"""Groq (OpenAI-compatible) — generate Short script + image prompts as JSON.

Supports two modes:
  • Single-language preset (legacy): returns full_narration, youtube_title, etc.
  • Multi-variant preset (bilingual): returns image_prompts once + variants[lang] = {title, desc, narration}.
"""
from __future__ import annotations

import json
import os
import re
import time
from typing import Any

from groq import BadRequestError, Groq, NotFoundError, RateLimitError

from pipeline.channel_presets import ChannelPreset
from pipeline.story_history import history_prompt_block

GROQ_MODEL = os.environ.get("GROQ_MODEL", "").strip() or "openai/gpt-oss-120b"

# Tried in order after GROQ_MODEL if Groq reports a model as not found
# (Groq retires models periodically — e.g. llama-3.1-8b-instant).
_FALLBACK_MODELS = [
    "openai/gpt-oss-120b",
    "openai/gpt-oss-20b",
    "llama-3.3-70b-versatile",
    "meta-llama/llama-4-scout-17b-16e-instruct",
    "qwen/qwen3-32b",
]
_NON_CHAT_MARKERS = ("whisper", "tts", "guard", "playai", "orpheus", "distil", "compound", "allam")
_dead_models: set[str] = set()
_active_model: str | None = None


_candidates_cache: list[str] | None = None


def _model_candidates(client: Groq) -> list[str]:
    global _candidates_cache
    if _candidates_cache is None:
        _candidates_cache = _discover_models(client)
    return [m for m in _candidates_cache if m not in _dead_models]


def _discover_models(client: Groq) -> list[str]:
    ordered = [GROQ_MODEL] + [m for m in _FALLBACK_MODELS if m != GROQ_MODEL]
    try:
        live = sorted(
            m.id
            for m in client.models.list().data
            if getattr(m, "active", True)
            and not any(k in m.id.lower() for k in _NON_CHAT_MARKERS)
        )
        # Keep preferred order for models that exist, then any other live chat models.
        ordered = [m for m in ordered if m in live] + [m for m in live if m not in ordered]
    except Exception as exc:  # listing is best-effort
        print(f"[groq] could not list models ({exc}); using static fallback list")
    return ordered


# ── Language-specific word-count guidance ──────────────────────────────
LANG_WORD_TARGETS = {
    "en": (
        75,
        95,
        "75-95 English words (~28-32 sec spoken aloud); "
        "tight punchy narration — shocking hook, surprising fact, memorable payoff. "
        "Every word earns its place. NOT a bullet list",
    ),
    "hi": (
        135,
        170,
        "135-170 Devanagari Hindi words — aim ~150 (~55-70 sec); full sentences, not headlines",
    ),
}

# Bilingual presets override per variant; these are fallbacks only.
DEFAULT_MIN_WORDS = {"hi": 80, "en": 120}


def _lang_label(lang: str) -> str:
    return {"en": "English", "hi": "Hindi (Devanagari script)"}.get(lang, lang)


def _build_hashtag_string(preset: ChannelPreset) -> str:
    tags = preset.get("description_hashtags") or []
    base = " ".join(f"#{t}" for t in tags)
    return f"{base} #Shorts #YouTubeShorts".strip()


def _build_youtube_description(preset: ChannelPreset, hook: str, context: str) -> str:
    hook = hook.strip()
    context = context.strip()
    hashtags = _build_hashtag_string(preset)
    return f"{hook}\n\n{context}\n\n{hashtags}"


def _parse_json_response(raw: str) -> dict[str, Any]:
    """Parse model JSON; merge consecutive objects if the model split its output."""
    try:
        data = json.loads(raw)
        if isinstance(data, dict):
            return data
    except json.JSONDecodeError:
        pass

    merged: dict[str, Any] = {}
    for match in re.finditer(r"\{[^{}]*(?:\{[^{}]*\}[^{}]*)*\}", raw, re.DOTALL):
        try:
            obj = json.loads(match.group())
        except json.JSONDecodeError:
            continue
        if isinstance(obj, dict):
            merged.update(obj)

    if merged:
        return merged
    raise ValueError("Could not parse JSON from model output")


def _normalize_single_pack(data: dict[str, Any], preset: ChannelPreset) -> dict[str, Any]:
    """Ensure required fields exist; build youtube_description from simpler parts."""
    if not (data.get("youtube_description") or "").strip():
        hook = (data.get("description_hook") or data.get("youtube_title") or "").strip()
        context = (data.get("description_context") or "").strip()
        if hook and context:
            data["youtube_description"] = _build_youtube_description(preset, hook, context)
    return data


def generate_short_pack(
    preset: ChannelPreset,
    *,
    topic_hint: str | None = None,
    channel_id: str | None = None,
) -> dict[str, Any]:
    topic_hint = (topic_hint or os.environ.get("SHORT_TOPIC", "")).strip()

    user = (
        f"Channel style: {preset['label']}.\n"
        f"Create ONE YouTube Short.\n"
    )
    if topic_hint:
        user += f"Topic idea from creator: {topic_hint}\n"

    if channel_id:
        anti_repeat = history_prompt_block(channel_id)
        if anti_repeat:
            user += anti_repeat

    n = preset["segment_count"]
    variants = preset.get("variants") or []

    if variants:
        return _generate_multivariant(preset, user, n, variants)
    return _generate_single(preset, user, n)


# ─────────────────────────────────────────────────────────────────────────
# Single-language path (backward compat for world_facts, etc.)
# ─────────────────────────────────────────────────────────────────────────
def _generate_single(preset: ChannelPreset, user: str, n: int) -> dict[str, Any]:
    language = (preset.get("language") or "en").lower()
    lo, hi, blurb = LANG_WORD_TARGETS.get(language, LANG_WORD_TARGETS["en"])

    if language == "hi":
        narration_rule = (
            '"full_narration": "COMPLETE narration as ONE continuous paragraph in Devanagari Hindi. '
            f'This is what the voice will read aloud. MUST be {blurb}. '
            'Natural spoken Hindi — no segment markers, no numbering, no English transliteration."'
        )
        strict_extra = (
            "- LANGUAGE: full_narration, youtube_title, and youtube_description MUST be in Devanagari Hindi.\n"
            "- image_prompts MUST be in ENGLISH (the image model does not understand Hindi).\n"
            f"- WORD COUNT: full_narration MUST contain {lo}-{hi} Hindi words.\n"
        )
    else:
        narration_rule = (
            '"full_narration": "COMPLETE narration as one continuous paragraph. This is what the voice will read. '
            f'Must be {blurb}. Natural narration — no segment breaks, no numbering."'
        )
        strict_extra = f"- full_narration is ONE continuous paragraph, {lo}-{hi} English words.\n"

    user += f"""
Return ONLY one valid JSON object (not multiple). Use exactly these keys:
{{
  "youtube_title": "short catchy title, under 90 chars, no hashtags",
  "description_hook": "one hook sentence with a relevant emoji, under 80 chars",
  "description_context": "exactly two sentences: what the viewer will learn about this fact",
  {narration_rule},
  "image_prompts": [
    "visual description for image 1: setting, subject, action. No style words. No text in image.",
    "visual description for image 2...",
    "..."
  ]
}}

JSON RULES (critical):
- Output ONE JSON object only — never split into multiple objects.
- Do NOT put description lines as separate top-level keys.
- Use plain strings for every value; no markdown fences.

STRICT RULES:
{strict_extra}- "image_prompts" array MUST have exactly {n} entries.
- Each image_prompt matches a different moment/beat in order.
- Image prompts are just visuals — no narration text, no style words, no quotes.
- The narration must flow naturally as one spoken piece (no "segment 1", "segment 2" etc).
- Stay on the topic idea from the creator; do not switch to an unrelated fact.
"""

    max_attempts = 3
    last_err = ""
    for attempt in range(max_attempts):
        extra = ""
        if attempt > 0:
            extra = (
                f"\n\nCRITICAL: Previous attempt failed validation: {last_err}.\n"
                "Return ONE valid JSON object with keys youtube_title, description_hook, "
                "description_context, full_narration, image_prompts. "
                f"Expand full_narration to {lo}-{hi} words if it was too short.\n"
            )

        temp = 0.7 if attempt == 0 else 0.45
        data = _call_groq(preset, user + extra, temperature=temp)
        data = _normalize_single_pack(data, preset)

        try:
            narration = data.get("full_narration", "").strip()
            if not narration:
                raise ValueError("Missing full_narration")

            if not (data.get("youtube_title") or "").strip():
                raise ValueError("Missing youtube_title")

            prompts = data.get("image_prompts")
            if not isinstance(prompts, list) or len(prompts) != n:
                raise ValueError(f"Expected {n} image_prompts, got {len(prompts or [])}")
            for i, p in enumerate(prompts):
                if not isinstance(p, str) or not p.strip():
                    raise ValueError(f"image_prompt {i} is empty")

            word_count = len(narration.split())
            min_words = preset.get("min_words", DEFAULT_MIN_WORDS.get(language, 80))
            if word_count < min_words:
                raise ValueError(
                    f"Narration too short ({word_count} words, expected ≥ {min_words} for {language})"
                )

            return data
        except ValueError as e:
            last_err = str(e)
            if attempt == max_attempts - 1:
                raise

    # Fallback (should be unreachable due to raise above)
    return data


# ─────────────────────────────────────────────────────────────────────────
# Multi-variant path (one Groq call returns every language's narration)
# ─────────────────────────────────────────────────────────────────────────
def _generate_multivariant(
    preset: ChannelPreset, user: str, n: int, variants: list,
) -> dict[str, Any]:
    hashtag_str = _build_hashtag_string(preset)
    # Build the per-language requirement lines
    lang_lines = []
    for v in variants:
        lang = v["lang"]
        lo, hi, blurb = LANG_WORD_TARGETS.get(lang, LANG_WORD_TARGETS["en"])
        lang_lines.append(
            f'    "{lang}": {{\n'
            f'      "youtube_title": "catchy title in {_lang_label(lang)} (<90 chars, no hashtags)",\n'
            f'      "youtube_description": "Line 1: hook sentence with emoji in {_lang_label(lang)} (<80 chars). '
            f'Line 2: blank. Line 3-4: 2 context sentences in {_lang_label(lang)}. '
            f'Line 5: blank. Line 6: copy verbatim: {hashtag_str}",\n'
            f'      "full_narration": "ONE continuous paragraph in {_lang_label(lang)}. '
            f'{blurb}. Natural spoken narration, no segment markers."\n'
            f'    }}'
        )
    variants_block = ",\n".join(lang_lines)

    word_targets = "\n".join(
        f"  - {_lang_label(v['lang'])}: {LANG_WORD_TARGETS.get(v['lang'], LANG_WORD_TARGETS['en'])[2]}"
        for v in variants
    )
    lang_keys = ", ".join(f'"{v["lang"]}"' for v in variants)

    user += f"""
Return ONLY valid JSON with this shape:
{{
  "image_prompts": [
    "visual description for image 1 — IN ENGLISH ONLY: setting, subject, action. No style words. No text in image.",
    "visual description for image 2 — in English…",
    "..."
  ],
  "variants": {{
{variants_block}
  }}
}}

STRICT RULES:
- "image_prompts" array MUST have exactly {n} entries, ALL in English.
- "variants" object MUST contain keys: {lang_keys}.
- Each variant tells the SAME facts/story but written natively in that language (not literal translation).
- Word-count targets per language:
{word_targets}
- Narrations are continuous spoken paragraphs — no segment numbers, no headings.
- Titles/descriptions: each in its own language.
- BEFORE you output JSON: mentally count words in each full_narration. If English is under 115 words OR Hindi under 100 words, REWRITE that paragraph longer (same facts) until counts are met.
"""

    last_err: str | None = None
    max_attempts = 4
    for attempt in range(max_attempts):
        extra = ""
        if last_err:
            extra = (
                "\n\n=== REGENERATE (previous JSON failed validation) ===\n"
                f"{last_err}\n"
                "Return a NEW complete JSON object that fixes the issue. "
                "Keep the same facts/story and the same image_prompts beats; "
                "expand ONLY the narration(s) that were too short — add 3-5 full sentences each.\n"
            )
        # Later attempts: lower temperature so the model obeys length constraints more reliably.
        temp = 0.85 if attempt < 2 else 0.45
        data = _call_groq(preset, user + extra, temperature=temp)
        try:
            _assert_multivariant_valid(data, variants, n)
            return data
        except ValueError as e:
            last_err = str(e)
            if attempt == max_attempts - 1:
                raise


def _assert_multivariant_valid(data: dict[str, Any], variants: list, n: int) -> None:
    prompts = data.get("image_prompts")
    if not isinstance(prompts, list) or len(prompts) != n:
        raise ValueError(f"Expected {n} image_prompts, got {len(prompts or [])}")
    for i, p in enumerate(prompts):
        if not isinstance(p, str) or not p.strip():
            raise ValueError(f"image_prompt {i} is empty")

    vmap = data.get("variants")
    if not isinstance(vmap, dict):
        raise ValueError("Groq response missing 'variants' object")

    for v in variants:
        lang = v["lang"]
        node = vmap.get(lang)
        if not isinstance(node, dict):
            raise ValueError(f"variants['{lang}'] missing")

        narration = (node.get("full_narration") or "").strip()
        if not narration:
            raise ValueError(f"variants['{lang}'].full_narration empty")

        min_words = v.get("min_words", DEFAULT_MIN_WORDS.get(lang, 80))
        word_count = len(narration.split())
        if word_count < min_words:
            lo, hi, _ = LANG_WORD_TARGETS.get(lang, LANG_WORD_TARGETS["en"])
            raise ValueError(
                f"variants['{lang}'].full_narration too short "
                f"({word_count} words, need ≥{min_words}; ideal range {lo}-{hi})"
            )

        if not (node.get("youtube_title") or "").strip():
            raise ValueError(f"variants['{lang}'].youtube_title empty")


def _create_with_fallback(client: Groq, **kwargs: Any):
    """chat.completions.create, switching models if the current one is retired/unavailable."""
    global _active_model
    candidates = [_active_model] if _active_model else []
    candidates += [m for m in _model_candidates(client) if m not in candidates]
    last_exc: Exception | None = None
    for model in candidates:
        call_kwargs = dict(kwargs)
        if model.startswith("openai/gpt-oss"):
            # Reasoning model: keep thinking short so it doesn't eat the output budget.
            call_kwargs["reasoning_effort"] = "low"
            call_kwargs["max_tokens"] = max(call_kwargs.get("max_tokens", 0), 4096)
        try:
            resp = _create_rate_limited(client, model, call_kwargs)
            if model != GROQ_MODEL and _active_model != model:
                print(f"[groq] model '{GROQ_MODEL}' unavailable - using '{model}'")
            _active_model = model
            return resp
        except (NotFoundError, _QuotaExhausted) as exc:
            why = "quota exhausted" if isinstance(exc, _QuotaExhausted) else "not found"
            print(f"[groq] model '{model}' {why}, trying next...")
            _dead_models.add(model)
            if _active_model == model:
                _active_model = None
            last_exc = exc
    raise RuntimeError(f"No usable Groq model found (tried: {', '.join(candidates)})") from last_exc


class _QuotaExhausted(Exception):
    """Rate limit that won't clear within this run (e.g. tokens-per-day)."""


def _retry_after_seconds(exc: RateLimitError) -> float:
    headers = getattr(getattr(exc, "response", None), "headers", None) or {}
    try:
        return float(headers.get("retry-after", "") or 0)
    except ValueError:
        return 0.0


def _create_rate_limited(client: Groq, model: str, kwargs: dict[str, Any]):
    """Retry per-minute limits (free tier is ~8k tokens/min); give up on daily limits."""
    for attempt in range(6):
        try:
            return client.chat.completions.create(model=model, **kwargs)
        except RateLimitError as exc:
            wait = _retry_after_seconds(exc)
            msg = str(exc).lower()
            if "per day" in msg or "(tpd)" in msg or "(rpd)" in msg or wait > 180:
                raise _QuotaExhausted(str(exc)) from exc
            wait = min(max(wait, 10.0 * (attempt + 1)), 90.0)
            print(f"[groq] rate limited on '{model}', waiting {wait:.0f}s...")
            time.sleep(wait)
    raise _QuotaExhausted(f"still rate limited on {model} after retries")


def chat_text(
    system: str,
    user: str,
    *,
    max_tokens: int = 4096,
    temperature: float = 0.7,
) -> str:
    """Plain-text completion (used for writing animated scene code)."""
    api_key = os.environ.get("GROQ_API_KEY", "").strip()
    if not api_key:
        raise RuntimeError("GROQ_API_KEY is not set.")
    client = Groq(api_key=api_key)
    resp = _create_with_fallback(
        client,
        messages=[{"role": "system", "content": system}, {"role": "user", "content": user}],
        temperature=temperature,
        max_tokens=max_tokens,
    )
    return resp.choices[0].message.content or ""


def _call_groq(
    preset: ChannelPreset,
    user: str,
    *,
    temperature: float = 0.85,
) -> dict[str, Any]:
    api_key = os.environ.get("GROQ_API_KEY", "").strip()
    if not api_key:
        raise RuntimeError(
            "GROQ_API_KEY is not set. "
            "Local: add it to your .env file. "
            "GitHub Actions: add it as a repository secret named GROQ_API_KEY."
        )
    client = Groq(api_key=api_key)
    json_retry_hint = (
        "\n\nREMINDER: Respond with ONE JSON object only. "
        "Keys must be valid JSON strings — no extra objects, no blank keys."
    )

    last_error: Exception | None = None
    for attempt in range(4):
        prompt = user if attempt == 0 else user + json_retry_hint
        temp = temperature if attempt == 0 else min(temperature, 0.45)
        try:
            resp = _create_with_fallback(
                client,
                messages=[
                    {"role": "system", "content": preset["groq_system_hint"]},
                    {"role": "user", "content": prompt},
                ],
                temperature=temp,
                max_tokens=2048,
                response_format={"type": "json_object"},
            )
            raw = resp.choices[0].message.content
            if not raw:
                raise RuntimeError("Empty Groq response")
            return _parse_json_response(raw)
        except BadRequestError as exc:
            last_error = exc
            failed = ""
            body = getattr(exc, "body", None)
            if isinstance(body, dict):
                failed = (body.get("error") or {}).get("failed_generation") or ""
            if failed:
                try:
                    return _normalize_single_pack(_parse_json_response(failed), preset)
                except ValueError:
                    pass
            if attempt < 3:
                time.sleep(1.5 * (attempt + 1))
                continue
            raise
        except (json.JSONDecodeError, ValueError) as exc:
            last_error = exc
            if attempt < 3:
                time.sleep(1.0)
                continue
            raise RuntimeError(f"Groq returned invalid JSON: {exc}") from exc

    raise RuntimeError(f"Groq call failed after retries: {last_error}")
