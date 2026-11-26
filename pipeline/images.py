"""Image generation: DeAPI.ai (paid) or Pollinations.ai (free, no key needed)."""
from __future__ import annotations

import os
import random
import time
import urllib.parse
from pathlib import Path

import httpx

DEAPI_SUBMIT_URL = "https://api.deapi.ai/api/v1/client/txt2img"
DEAPI_POLL_URL = "https://api.deapi.ai/api/v1/client/request-status"

POLLINATIONS_URL = "https://image.pollinations.ai/prompt/{prompt}"

STYLE_SUFFIX = (
    ", cinematic digital illustration, detailed scene art, strong composition, "
    "professional youtube visual quality, no text, no captions, no watermark, no logos"
)

DEFAULT_NEGATIVE = (
    "blurry, low quality, watermark, logo, text, title, signature, ugly, grainy, "
    "gore, blood, nudity, child-unsafe"
)


def full_visual_prompt(scene: str, style_suffix: str | None = None) -> str:
    """Combine the scene description with a channel-specific style suffix."""
    return f"{scene.strip()}{(style_suffix or STYLE_SUFFIX)}"


def _deapi_generate(
    prompt: str,
    *,
    api_key: str,
    width: int,
    height: int,
    model: str,
    max_polls: int = 30,
    poll_interval: float = 3.0,
) -> bytes:
    """Submit image job, poll until done, download result."""
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
        "Accept": "application/json",
    }

    # Step 1: Submit
    payload = {
        "prompt": prompt,
        "model": model,
        "width": width,
        "height": height,
        "steps": 4,
        "seed": random.randint(1, 999999),
    }

    with httpx.Client(timeout=60.0) as client:
        # Submit with retry on 429
        for submit_try in range(5):
            resp = client.post(DEAPI_SUBMIT_URL, json=payload, headers=headers)
            if resp.status_code == 429:
                wait = 15 * (submit_try + 1)
                print(f"      DeAPI 429 on submit — waiting {wait}s (try {submit_try + 1}/5)…")
                time.sleep(wait)
                continue
            resp.raise_for_status()
            break
        else:
            raise RuntimeError("DeAPI: 429 on submit after 5 retries")

        data = resp.json()

        request_id = data.get("data", {}).get("request_id")
        if not request_id:
            raise RuntimeError(f"No request_id in DeAPI response: {data}")
        print(f"      DeAPI submitted (id: {request_id})")

        # Step 2: Poll
        poll_headers = {
            "Authorization": f"Bearer {api_key}",
            "Accept": "application/json",
        }

        for attempt in range(1, max_polls + 1):
            time.sleep(poll_interval)

            poll_resp = client.get(
                f"{DEAPI_POLL_URL}/{request_id}",
                headers=poll_headers,
                timeout=30.0,
            )
            poll_resp.raise_for_status()
            poll_data = poll_resp.json()

            status = poll_data.get("data", {}).get("status", "")

            if status in ("completed", "success", "done"):
                image_url = poll_data["data"].get("result_url")
                if not image_url:
                    raise RuntimeError(f"Completed but no result_url: {poll_data}")

                img_resp = client.get(image_url, timeout=60.0)
                img_resp.raise_for_status()
                print(f"      DeAPI done (polled {attempt}x)")
                return img_resp.content

            if status in ("failed", "error"):
                raise RuntimeError(f"DeAPI image failed: {poll_data}")

            # Still processing — keep polling

        raise RuntimeError(f"DeAPI timed out after {max_polls} polls for {request_id}")


def _pollinations_generate(
    prompt: str,
    *,
    width: int,
    height: int,
    seed: int | None = None,
    retries: int = 3,
) -> bytes:
    """Fetch an image from Pollinations.ai.

    With POLLINATIONS_API_KEY set (create one at enter.pollinations.ai) this uses the
    keyed gen.pollinations.ai endpoint. Without a key it uses the anonymous endpoint,
    which only allows a few images per IP before answering 402 Payment Required.
    """
    encoded = urllib.parse.quote(prompt)
    s = seed if seed is not None else random.randint(1, 999999)
    key = os.environ.get("POLLINATIONS_API_KEY", "").strip()
    model = os.environ.get("POLLINATIONS_MODEL", "flux").strip() or "flux"
    if key:
        url = (
            f"https://gen.pollinations.ai/image/{encoded}"
            f"?model={model}&width={width}&height={height}&seed={s}&nologo=true&enhance=false"
        )
        headers = {"Authorization": f"Bearer {key}"}
    else:
        url = (
            f"https://image.pollinations.ai/prompt/{encoded}"
            f"?width={width}&height={height}&seed={s}&nologo=true&enhance=false"
        )
        headers = {}
    with httpx.Client(timeout=120.0, follow_redirects=True) as client:
        for attempt in range(1, retries + 1):
            try:
                resp = client.get(url, headers=headers)
                if resp.status_code in (401, 402, 403):
                    hint = (
                        "Pollinations rejected the API key or its balance is empty (top up at enter.pollinations.ai)"
                        if key else
                        "Pollinations now needs an API key: set POLLINATIONS_API_KEY or DEAPI_TOKEN"
                    )
                    raise RuntimeError(f"{hint} (HTTP {resp.status_code})")
                resp.raise_for_status()
                if not resp.headers.get("content-type", "").startswith("image/"):
                    raise RuntimeError(f"Pollinations returned {resp.headers.get('content-type')!r}, not an image")
                return resp.content
            except RuntimeError:
                raise  # auth/billing problems won't fix themselves with a retry
            except Exception as exc:
                if attempt == retries:
                    raise
                wait = 5 * attempt
                print(f"      Pollinations retry {attempt}/{retries} after {wait}s: {exc}")
                time.sleep(wait)
    raise RuntimeError("Pollinations: all retries exhausted")


def save_scene_image(
    index: int,
    prompt: str,
    out_path: Path,
    *,
    width: int = 768,
    height: int = 768,
    negative: str = DEFAULT_NEGATIVE,
) -> tuple[str, str]:
    """Generate and save one image. Returns (status, detail).

    Uses DeAPI if DEAPI_TOKEN is set, otherwise falls back to Pollinations.ai (free).
    """
    out_path = Path(out_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)

    api_key = os.environ.get("DEAPI_TOKEN", "").strip()

    if api_key:
        model = os.environ.get("DEAPI_MODEL", "Flux_2_Klein_4B_BF16")
        try:
            img_bytes = _deapi_generate(
                prompt,
                api_key=api_key,
                width=width,
                height=height,
                model=model,
            )
            out_path.write_bytes(img_bytes)
            return "ok", "deapi"
        except Exception as e:
            print(f"      DeAPI failed, falling back to Pollinations: {e}")

    # Free fallback — no key needed
    try:
        img_bytes = _pollinations_generate(prompt, width=width, height=height)
        out_path.write_bytes(img_bytes)
        return "ok", "pollinations"
    except Exception as e:
        return "fail", str(e)
