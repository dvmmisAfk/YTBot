"""Motion-graphics Short renderer (HyperFrames).

Pipeline:  narration words (Edge TTS word timings)
        →  scene plan (one scene per sentence, merged/capped)
        →  AI-written scene per beat (pipeline.motion_scenes), validated with
           `hyperframes check`, retried once with the errors, else a built-in
           fallback scene
        →  root composition (animated background, scenes, word-synced captions,
           voiceover + BGM)
        →  `hyperframes render` → MP4
"""
from __future__ import annotations

import hashlib
import html as html_lib
import json
import os
import random
import re
import shutil
import subprocess
import time
from pathlib import Path
from typing import Any

from pipeline import motion_scenes as ms

HF_VERSION = os.environ.get("HYPERFRAMES_VERSION", "0.9.96")
FPS = 30
MAX_SCENES = int(os.environ.get("MOTION_MAX_SCENES", "6"))
MIN_SCENE_S = 2.4

PALETTES = [
    {"name": "electric", "bg1": "#070b24", "bg2": "#1c2a7a", "glow1": "#3b5bff", "glow2": "#00d1b2",
     "ink": "#ffffff", "accent": "#ffd23f", "accent2": "#3ee6c1", "muted": "#9fb1ff"},
    {"name": "sunset", "bg1": "#1a0526", "bg2": "#6b1650", "glow1": "#ff4d6d", "glow2": "#ff9e00",
     "ink": "#ffffff", "accent": "#ffc300", "accent2": "#ff6b9a", "muted": "#f2b5d4"},
    {"name": "ocean", "bg1": "#011627", "bg2": "#04506b", "glow1": "#00b4d8", "glow2": "#48cae4",
     "ink": "#ffffff", "accent": "#ffd166", "accent2": "#5ef0ff", "muted": "#a9def9"},
    {"name": "forest", "bg1": "#07150e", "bg2": "#18452c", "glow1": "#2dc653", "glow2": "#b5e48c",
     "ink": "#ffffff", "accent": "#d9ed92", "accent2": "#ffcf56", "muted": "#b7e4c7"},
    {"name": "volcano", "bg1": "#140606", "bg2": "#4a0f0f", "glow1": "#e63946", "glow2": "#f77f00",
     "ink": "#ffffff", "accent": "#fcbf49", "accent2": "#ff7b54", "muted": "#f4a9a8"},
]


# ── scene planning ─────────────────────────────────────────────────────────

def plan_scenes(words: list[dict[str, Any]], total: float) -> list[dict[str, Any]]:
    """Group words into scenes on sentence boundaries; returns [{start, end, words, text}]."""
    groups: list[list[dict]] = []
    for w in words:
        if not groups or groups[-1][-1]["sentence"] != w["sentence"]:
            groups.append([])
        groups[-1].append(w)

    def span(g: list[dict]) -> float:
        return g[-1]["end"] - g[0]["start"]

    # merge short sentences into a neighbour
    changed = True
    while changed and len(groups) > 1:
        changed = False
        for i, g in enumerate(groups):
            if span(g) < MIN_SCENE_S:
                j = i - 1 if i == len(groups) - 1 else (i + 1 if i == 0 else (i - 1 if span(groups[i - 1]) < span(groups[i + 1]) else i + 1))
                a, b = sorted((i, j))
                groups[a:b + 1] = [groups[a] + groups[b]]
                changed = True
                break
    # cap the scene count by merging the shortest adjacent pair
    while len(groups) > MAX_SCENES:
        i = min(range(len(groups) - 1), key=lambda k: span(groups[k]) + span(groups[k + 1]))
        groups[i:i + 2] = [groups[i] + groups[i + 1]]

    scenes = []
    for i, g in enumerate(groups):
        start = 0.0 if i == 0 else round(g[0]["start"] - 0.08, 3)
        scenes.append({"words": g, "start": start, "text": " ".join(w["text"] for w in g)})
    for i, s in enumerate(scenes):
        s["end"] = scenes[i + 1]["start"] if i + 1 < len(scenes) else total
        s["duration"] = round(s["end"] - s["start"], 3)
        s["local_words"] = [{"text": w["text"], "t": round(w["start"] - s["start"], 2)} for w in s["words"]]
    return scenes


# ── composition files ──────────────────────────────────────────────────────

def _root_html(palette: dict, scenes: list[dict], total: float, vo_dur: float) -> str:
    hosts = "\n".join(
        f'      <div id="s{i + 1}" data-composition-id="s{i + 1}" data-composition-src="compositions/s{i + 1}.html" '
        f'data-start="{s["start"]:.3f}" data-duration="{s["duration"]:.3f}" data-track-index="1" '
        f'data-track-kind="graphics" data-width="{ms.W}" data-height="{ms.H}" style="z-index:2"></div>'
        for i, s in enumerate(scenes)
    )
    p = palette
    return f"""<!doctype html>
<html lang="en">
  <head>
    <meta charset="UTF-8" />
    <meta name="viewport" content="width={ms.W}, height={ms.H}" />
    <script src="https://cdn.jsdelivr.net/npm/gsap@3.15.0/dist/gsap.min.js"></script>
    <style>
      :root {{
        --bg1: {p['bg1']}; --bg2: {p['bg2']}; --glow1: {p['glow1']}; --glow2: {p['glow2']};
        --ink: {p['ink']}; --accent: {p['accent']}; --accent2: {p['accent2']}; --muted: {p['muted']};
        --panel: rgba(255, 255, 255, 0.10);
        --font-display: "Archivo Black", "Montserrat", sans-serif;
        --font-body: "Montserrat", "Inter", sans-serif;
      }}
      * {{ margin: 0; padding: 0; box-sizing: border-box; }}
      html, body {{ width: {ms.W}px; height: {ms.H}px; overflow: hidden; background: var(--bg1); }}
      #root {{ width: 100%; height: 100%; position: relative; overflow: hidden; font-family: var(--font-body); }}
      #bg {{ position: absolute; inset: 0; background: linear-gradient(160deg, var(--bg1) 0%, var(--bg2) 100%); z-index: 0; }}
      .bg-blob {{ position: absolute; width: 1100px; height: 1100px; border-radius: 50%; opacity: 0.55; }}
      #bg-b1 {{ left: -420px; top: -260px; background: radial-gradient(circle, var(--glow1) 0%, transparent 65%); }}
      #bg-b2 {{ left: 380px; top: 1000px; background: radial-gradient(circle, var(--glow2) 0%, transparent 65%); }}
      #bg-grid {{ position: absolute; inset: 0; opacity: 0.10;
        background-image: radial-gradient(rgba(255,255,255,0.9) 2px, transparent 2px); background-size: 54px 54px; }}
      #bg-vignette {{ position: absolute; inset: 0; background: radial-gradient(ellipse at center, transparent 55%, rgba(0,0,0,0.55) 100%); }}
    </style>
  </head>
  <body>
    <div id="root" data-composition-id="main" data-start="0" data-duration="{total:.3f}" data-width="{ms.W}" data-height="{ms.H}">
      <div id="bg" data-layout-ignore>
        <div id="bg-b1" class="bg-blob"></div>
        <div id="bg-b2" class="bg-blob"></div>
        <div id="bg-grid"></div>
        <div id="bg-vignette"></div>
      </div>
{hosts}
      <div id="captions" data-composition-id="captions" data-composition-src="compositions/captions.html" data-start="0" data-duration="{total:.3f}" data-track-index="2" data-track-kind="captions" data-width="{ms.W}" data-height="{ms.H}" style="z-index:5"></div>
      <audio id="vo" class="clip" src="assets/voiceover.mp3" data-start="0" data-duration="{vo_dur:.3f}" data-track-index="3" data-volume="1"></audio>
      <audio id="bgm" class="clip" src="assets/bgm.mp3" data-start="0" data-duration="{total:.3f}" data-track-index="4" data-volume="0.18" data-fade-in="0.5" data-fade-out="1.2"></audio>
    </div>
    <script>
      const tl = gsap.timeline({{ paused: true }});
      const D = {total:.3f};
      tl.fromTo("#bg-b1", {{ x: 0, y: 0, scale: 1 }}, {{ x: 260, y: 520, scale: 1.25, duration: D, ease: "sine.inOut" }}, 0);
      tl.fromTo("#bg-b2", {{ x: 0, y: 0, scale: 1.1 }}, {{ x: -380, y: -560, scale: 0.9, duration: D, ease: "sine.inOut" }}, 0);
      tl.fromTo("#bg-grid", {{ y: 0 }}, {{ y: -54 * Math.round(D), duration: D, ease: "none" }}, 0);
      window.__timelines["main"] = tl;
      tl.seek(0);
    </script>
  </body>
</html>
"""


def _caption_groups(words: list[dict[str, Any]], max_words: int = 3) -> list[list[dict]]:
    groups: list[list[dict]] = []
    for w in words:
        g = groups[-1] if groups else None
        if (
            g is None
            or len(g) >= max_words
            or g[-1]["sentence"] != w["sentence"]
            or w["start"] - g[-1]["end"] >= 0.15
            or re.search(r"[,;:]$", g[-1]["text"])
        ):
            groups.append([])
        groups[-1].append(w)
    return groups


def _captions_html(words: list[dict[str, Any]], total: float, palette: dict) -> str:
    groups = _caption_groups(words)
    rows, js = [], []
    for gi, g in enumerate(groups):
        start = max(0.12, g[0]["start"] - 0.05)
        end = min(groups[gi + 1][0]["start"] - 0.02, total) if gi + 1 < len(groups) else min(g[-1]["end"] + 0.6, total)
        end = max(end, start + 0.25)
        n_chars = sum(len(w["text"]) for w in g) + len(g) - 1
        size = 80 if n_chars <= 12 else max(48, int(80 * 12 / n_chars))
        spans = "".join(
            f'<span id="cap-g{gi}-w{wi}" class="cap-word">{html_lib.escape(w["text"].upper())}</span> '
            for wi, w in enumerate(g)
        )
        rows.append(f'<div id="cap-g{gi}" class="cap-group" style="font-size:{size}px"><span class="cap-inner">{spans.strip()}</span></div>')
        js.append(f'tl.set("#cap-g{gi}", {{ opacity: 1, visibility: "visible" }}, {start:.3f});')
        js.append(f'tl.fromTo("#cap-g{gi} .cap-inner", {{ scale: 0.82, y: 18 }}, {{ scale: 1, y: 0, duration: 0.16, ease: "back.out(2.2)" }}, {start:.3f});')
        for wi, w in enumerate(g):
            js.append(f'tl.set("#cap-g{gi}-w{wi}", {{ color: "{palette['accent']}" }}, {max(start, w["start"]):.3f});')
            if wi < len(g) - 1:
                js.append(f'tl.set("#cap-g{gi}-w{wi}", {{ color: "{palette['ink']}" }}, {max(start, g[wi + 1]["start"]):.3f});')
        js.append(f'tl.set("#cap-g{gi}", {{ opacity: 0, visibility: "hidden" }}, {end:.3f});')
    body = "\n    ".join(rows)
    script = "\n      ".join(js)
    return f"""<template>
  <style>
    #root {{ position: absolute; inset: 0; }}
    .cap-group {{ position: absolute; left: {ms.SAFE['x0']}px; top: {ms.CAPTION_TOP}px; width: {ms.SAFE['x1'] - ms.SAFE['x0']}px; height: 160px;
      display: flex; align-items: center; justify-content: center; text-align: center;
      opacity: 0; visibility: hidden; overflow: visible; font-family: "Montserrat", sans-serif; font-weight: 900; }}
    .cap-inner {{ display: inline-block; padding: 10px 26px; border-radius: 22px; background: rgba(0, 0, 0, 0.38);
      line-height: 1.05; letter-spacing: 0.01em; color: {palette['ink']};
      text-shadow: 0 4px 0 rgba(0,0,0,0.55), 0 0 18px rgba(0,0,0,0.45); }}
  </style>
  <div id="root" data-composition-id="captions" data-width="{ms.W}" data-height="{ms.H}">
    {body}
  </div>
  <script>
    (function () {{
      const tl = gsap.timeline({{ paused: true }});
      {script}
      window.__timelines["captions"] = tl;
    }})();
  </script>
</template>
"""


# ── CLI helpers ────────────────────────────────────────────────────────────

def _hf_cmd() -> list[str]:
    custom = os.environ.get("HYPERFRAMES_CMD", "").strip()
    if custom:
        return custom.split()
    npx = shutil.which("npx") or shutil.which("npx.cmd") or "npx"
    return [npx, "--yes", f"hyperframes@{HF_VERSION}"]


def _hf_env() -> dict[str, str]:
    env = dict(os.environ)
    env.setdefault("HYPERFRAMES_SKIP_SKILLS", "1")
    env.setdefault("HYPERFRAMES_NO_UPDATE_CHECK", "1")
    # don't hand our API secrets to the CLI's environment
    for k in list(env):
        if k.startswith(("GROQ_", "YT_", "DEAPI_", "ELEVEN", "HF_TOKEN")):
            env.pop(k, None)
    return env


def _run_hf(args: list[str], cwd: Path, timeout: int) -> subprocess.CompletedProcess:
    return subprocess.run(
        _hf_cmd() + args, cwd=str(cwd), env=_hf_env(), capture_output=True,
        text=True, encoding="utf-8", errors="replace", timeout=timeout,
    )


# Layout findings worth one AI repair attempt (they don't break the render).
_FIXABLE_WARNINGS = {"outside_safe_zone", "content_overlap", "text_occluded", "text_clipped",
                     "text_overflow", "offscreen", "gsap_css_transform_conflict", "gsap_animates_clip_element",
                     "escaped_container", "container_overflow"}


def check_project(project: Path) -> tuple[dict[str, list[str]], dict[str, list[str]]]:
    """Run `hyperframes check --json`.

    Returns (errors, issues), each {composition key: [messages]}; the key is the
    scene id ("s3") for scene files, otherwise the file name.
    """
    res = _run_hf(["check", "--json", "--no-craft", "--no-cache", "--safe-zone", "shorts",
                   "--samples", "6", "--budget", "180s"], project, 420)
    out = res.stdout.strip()
    try:
        data = json.loads(out[out.find("{"):]) if "{" in out else {}
    except json.JSONDecodeError:
        data = {}
    if not data:
        raise RuntimeError(f"hyperframes check produced no JSON (exit {res.returncode}): {res.stderr[-800:]}")

    errors: dict[str, list[str]] = {}
    issues: dict[str, list[str]] = {}
    for section, body in data.items():
        if not isinstance(body, dict):
            continue
        for f in body.get("findings") or []:
            sev = str(f.get("severity", "")).lower()
            code = str(f.get("code", ""))
            if sev != "error" and code not in _FIXABLE_WARNINGS:
                continue
            src = str(f.get("sourceFile") or (f.get("dataAttributes") or {}).get("data-composition-file") or "")
            name = Path(src.replace("\\", "/")).name
            m = re.fullmatch(r"(s\d+)\.html", name)
            key = m.group(1) if m else (name or section)
            # runtime script errors are reported against index.html but name the scene
            sm = re.search(r"composition script error:\s*(s\d+)\b", str(f.get("message", "")))
            if sm:
                key = sm.group(1)
            text = f.get("text")
            msg = f"[{code}] {f.get('message', '')}" + (f' (text: "{text}")' if text else "")
            if f.get("fixHint"):
                msg += f" Fix: {f['fixHint']}"
            (errors if sev == "error" else issues).setdefault(key, []).append(msg[:400])
    return errors, issues


def render_project(project: Path, out_mp4: Path, quality: str) -> None:
    t0 = time.time()
    res = _run_hf(["render", "--quality", quality, "--fps", str(FPS), "--quiet", "-o", str(out_mp4.resolve())], project, 3000)
    if res.returncode != 0 or not out_mp4.exists() or out_mp4.stat().st_size < 50_000:
        raise RuntimeError(f"hyperframes render failed (exit {res.returncode}):\n{res.stdout[-1500:]}\n{res.stderr[-1500:]}")
    print(f"   rendered in {time.time() - t0:.0f}s → {out_mp4.stat().st_size / 1e6:.1f} MB")


# ── main entry ─────────────────────────────────────────────────────────────

def _write_scene(project: Path, sid: str, parts: dict[str, str], duration: float, seed: int) -> None:
    (project / "compositions" / f"{sid}.html").write_text(ms.wrap_scene(sid, parts, duration, seed), encoding="utf-8")


def _author_scene(scene: dict, idx: int, total_n: int, *, title: str, narration: str, previous: list[str],
                  feedback: str | None = None, prior: str | None = None) -> tuple[dict[str, str] | None, str, str]:
    """Ask the LLM for a scene. Returns (sanitised parts or None, raw reply, error)."""
    from pipeline.groq_script import chat_text

    sid = f"s{idx + 1}"
    user = ms.build_user_prompt(
        sid=sid, index=idx, total=total_n, title=title, narration=narration,
        sentence=scene["text"], duration=scene["duration"], words=scene["local_words"], previous=previous,
    )
    if feedback and prior:
        user += (
            "\n\nYOUR PREVIOUS ATTEMPT FAILED VALIDATION:\n" + feedback[:1500]
            + "\n\nPrevious attempt (fix it, keep the idea):\n" + prior[:5000]
        )
    try:
        raw = chat_text(ms.SYSTEM_PROMPT, user, max_tokens=4200, temperature=0.8 if not feedback else 0.4)
    except Exception as exc:  # quota / network — caller falls back
        return None, "", f"LLM call failed: {exc}"
    try:
        return ms.sanitize(ms.extract_blocks(raw), sid), raw, ""
    except ms.SceneError as exc:
        return None, raw, str(exc)


def build_motion_short(
    *,
    words: list[dict[str, Any]],
    vo_path: Path,
    vo_dur: float,
    title: str,
    narration: str,
    bgm_path: Path | None,
    run_dir: Path,
    out_mp4: Path,
) -> Path:
    project = run_dir / "motion"
    if project.exists():
        shutil.rmtree(project)
    (project / "compositions").mkdir(parents=True)
    (project / "assets").mkdir()
    shutil.copy(vo_path, project / "assets" / "voiceover.mp3")

    total = round(vo_dur + 0.7, 3)
    if bgm_path and bgm_path.exists():
        subprocess.run(
            ["ffmpeg", "-y", "-v", "error", "-stream_loop", "-1", "-i", str(bgm_path), "-t", f"{total:.3f}",
             "-c:a", "libmp3lame", "-b:a", "160k", str(project / "assets" / "bgm.mp3")],
            check=True,
        )
    else:  # silent track keeps the composition valid
        subprocess.run(
            ["ffmpeg", "-y", "-v", "error", "-f", "lavfi", "-i", "anullsrc=r=44100:cl=stereo", "-t", f"{total:.3f}",
             "-c:a", "libmp3lame", str(project / "assets" / "bgm.mp3")],
            check=True,
        )

    seed = int(hashlib.sha1(title.encode("utf-8")).hexdigest()[:8], 16)
    palette = random.Random(seed).choice(PALETTES)
    scenes = plan_scenes(words, total)
    print(f"   palette={palette['name']}  scenes={len(scenes)}  duration={total:.1f}s")

    (project / "hyperframes.json").write_text(json.dumps({"paths": {"blocks": "compositions", "assets": "assets"}}, indent=2))
    (project / "index.html").write_text(_root_html(palette, scenes, total, vo_dur), encoding="utf-8")
    (project / "compositions" / "captions.html").write_text(_captions_html(words, total, palette), encoding="utf-8")

    use_ai = os.environ.get("MOTION_AI_SCENES", "1") != "0"
    raws: dict[str, str] = {}
    status: dict[str, str] = {}
    previous: list[str] = []
    for i, sc in enumerate(scenes):
        sid = f"s{i + 1}"
        parts, err = None, "AI scenes disabled"
        if use_ai:
            parts, raws[sid], err = _author_scene(sc, i, len(scenes), title=title, narration=narration, previous=previous)
            if parts is None and raws.get(sid):
                print(f"   {sid}: rejected ({err}) — retrying")
                parts, raws[sid], err = _author_scene(sc, i, len(scenes), title=title, narration=narration,
                                                      previous=previous, feedback=err, prior=raws[sid])
        if parts is None:
            print(f"   {sid}: fallback scene ({err})")
            parts = ms.fallback_scene_parts(sid, sc["local_words"], sc["duration"], i)
            status[sid] = "fallback"
        else:
            status[sid] = "ai"
            print(f"   {sid}: AI scene ({sc['duration']:.1f}s)")
        previous.append(ms.scene_summary(parts))
        _write_scene(project, sid, parts, sc["duration"], seed + i)
        (project / "compositions" / f"{sid}.parts.json").write_text(ms.dumps(parts), encoding="utf-8")

    # Validate with the HyperFrames checker; repair or replace failing AI scenes.
    for round_no in range(2):
        errors, issues = check_project(project)
        bad = {k: v for k, v in errors.items() if re.fullmatch(r"s\d+", k)}
        other = {k: v for k, v in errors.items() if k not in bad}
        if other:
            print(f"   ⚠ check errors outside scenes: {json.dumps(other)[:600]}")
        # First round: AI scenes with layout problems also get one repair attempt.
        to_fix = dict(bad)
        if round_no == 0 and use_ai:
            for k, v in issues.items():
                if re.fullmatch(r"s\d+", k) and status.get(k) == "ai":
                    to_fix.setdefault(k, []).extend(v)
        if not to_fix:
            print("   ✓ hyperframes check passed" if not other else "   (continuing despite non-scene errors)")
            break
        for sid, msgs in to_fix.items():
            i = int(sid[1:]) - 1
            sc = scenes[i]
            fb = "\n".join(msgs)
            parts = None
            if sid not in bad:  # layout-only: try a repair, keep the original if the repair fails
                print(f"   {sid}: layout issues — asking AI to tidy ({msgs[0][:100]})")
                fixed, raw, err = _author_scene(sc, i, len(scenes), title=title, narration=narration,
                                                previous=previous[:i], feedback=fb, prior=raws.get(sid, ""))
                if fixed is not None:
                    raws[sid] = raw
                    _write_scene(project, sid, fixed, sc["duration"], seed + i)
                continue
            if round_no == 0 and status.get(sid) == "ai" and use_ai:
                print(f"   {sid}: check failed — asking AI to fix ({msgs[0][:120]})")
                parts, raw, err = _author_scene(sc, i, len(scenes), title=title, narration=narration,
                                                previous=previous[:i], feedback=fb, prior=raws.get(sid, ""))
                if parts is not None:
                    raws[sid] = raw
            if parts is None:
                print(f"   {sid}: replaced with fallback scene ({msgs[0][:120]})")
                parts = ms.fallback_scene_parts(sid, sc["local_words"], sc["duration"], i)
                status[sid] = "fallback"
            _write_scene(project, sid, parts, sc["duration"], seed + i)
    else:
        errors, _ = check_project(project)
        if any(re.fullmatch(r"s\d+", k) for k in errors):
            raise RuntimeError(f"scenes still failing check: {json.dumps(errors)[:800]}")

    (run_dir / "motion_status.json").write_text(json.dumps(status, indent=2))
    quality = os.environ.get("MOTION_RENDER_QUALITY", "looks")
    print(f"   rendering with HyperFrames {HF_VERSION} ({quality})…")
    render_project(project, out_mp4, quality)
    return out_mp4
