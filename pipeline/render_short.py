"""FFmpeg: images + audio + captions → vertical Short MP4 (9:16).

Fact/trivia effects stack:
  - Ken Burns zoom (alternating zoom-in / zoom-out)
  - Clean xfade transitions: fade, dissolve, slideleft
  - Bright documentary color grades — warm and vibrant
  - Background music: dobb.mp3 looped at 20% under narration
  - Bottom-center captions on the image footer (above letterbox bar)
"""
from __future__ import annotations

import random
import shutil
import subprocess
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
FONTS_DIR = REPO_ROOT / "assets" / "fonts"
BG_MUSIC_PATH = REPO_ROOT / "dobb.mp3"
DEFAULT_FONT_FILE = "Arial.ttf"
DEFAULT_FONT_NAME = "Arial"

FPS = 30
FADE_DUR = 0.5
ZOOM_AMOUNT = 0.10

XFADE_TRANSITIONS = [
    "fade",
    "dissolve",
    "slideleft",
    "slideright",
    "fade",
    "dissolve",
]

# Bright documentary palettes — one randomly selected per video
COLOR_PALETTES = [
    {"sat": 1.12, "bright": 0.04, "contrast": 1.06, "extra": ""},
    {"sat": 1.15, "bright": 0.05, "contrast": 1.04,
     "extra": "colorchannelmixer=rr=1.05:gg=1.02:bb=0.95"},
    {"sat": 1.10, "bright": 0.03, "contrast": 1.08,
     "extra": "colorchannelmixer=rr=0.95:gg=1.05:bb=1.08"},
    {"sat": 1.08, "bright": 0.06, "contrast": 1.05,
     "extra": "colorchannelmixer=rr=1.08:gg=1.04:bb=0.92"},
    {"sat": 1.14, "bright": 0.04, "contrast": 1.07,
     "extra": "colorchannelmixer=rr=1.02:gg=1.06:bb=1.00"},
]


def _clip_grade_vf(idx: int, n: int, palette: dict) -> str:
    """Per-clip color grade — slight brightening toward the payoff."""
    progress = idx / max(n - 1, 1)
    bright_bump = min(progress / 0.7, 1.0) * 0.03

    b = palette["bright"] + bright_bump
    c = palette["contrast"]
    vf = f"eq=saturation={palette['sat']:.2f}:brightness={b:.3f}:contrast={c:.2f}"
    if palette.get("extra"):
        vf += f",{palette['extra']}"
    return vf


def render_vertical_short(
    image_paths: list[Path],
    total_duration: float,
    audio_path: Path,
    sub_path: Path,
    out_video: Path,
    *,
    width: int = 1080,
    height: int = 1920,
    font_file: str = DEFAULT_FONT_FILE,
    font_name: str = DEFAULT_FONT_NAME,
) -> None:
    if not image_paths:
        raise ValueError("No images")
    if not shutil.which("ffmpeg"):
        raise RuntimeError(
            "ffmpeg not found. "
            "Ubuntu/GitHub Actions: sudo apt-get install ffmpeg  "
            "macOS: brew install ffmpeg  "
            "Windows: winget install ffmpeg"
        )

    out_video = Path(out_video)
    out_video.parent.mkdir(parents=True, exist_ok=True)
    tmp = out_video.parent / "_tmp_render"
    tmp.mkdir(parents=True, exist_ok=True)

    n = len(image_paths)
    clip_dur = (total_duration + (n - 1) * FADE_DUR) / n if n > 1 else total_duration
    frames_per_clip = max(int(clip_dur * FPS), 2)

    palette = random.choice(COLOR_PALETTES)

    # ── 1. Pre-scale images ──────────────────────────────────────────
    for i, src in enumerate(image_paths):
        dst = tmp / f"img_{i + 1:02d}.png"
        subprocess.run(
            [
                "ffmpeg", "-y", "-hide_banner", "-loglevel", "warning",
                "-i", str(src),
                "-vf", (f"scale={width}:{height}:force_original_aspect_ratio=decrease,"
                        f"pad={width}:{height}:(ow-iw)/2:(oh-ih)/2:black"),
                "-update", "1", "-frames:v", "1",
                str(dst),
            ],
            check=True,
            timeout=120,
        )

    # ── 2. Generate zoompan clips with per-clip color grading ────────
    for i in range(n):
        src_img = tmp / f"img_{i + 1:02d}.png"
        clip = tmp / f"clip_{i + 1:02d}.mp4"
        zoom_rate = ZOOM_AMOUNT / frames_per_clip

        if i % 2 == 0:
            zoom_expr = f"min(zoom+{zoom_rate:.8f},{1 + ZOOM_AMOUNT})"
        else:
            zoom_expr = f"if(eq(on,1),{1 + ZOOM_AMOUNT},max(zoom-{zoom_rate:.8f},1.0))"

        clip_grade = _clip_grade_vf(i, n, palette)
        vf = (
            f"zoompan=z='{zoom_expr}':"
            f"x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)':"
            f"d={frames_per_clip}:s={width}x{height}:fps={FPS},"
            f"format=yuv420p,"
            f"{clip_grade}"
        )

        subprocess.run(
            [
                "ffmpeg", "-y", "-hide_banner", "-loglevel", "warning",
                "-i", str(src_img),
                "-vf", vf,
                "-c:v", "libx264", "-preset", "ultrafast", "-crf", "15",
                str(clip),
            ],
            check=True,
            timeout=300,
        )

    # ── 3. Prepare subtitles + font ──────────────────────────────────
    shutil.copyfile(sub_path, tmp / "captions.ass")

    fontsdir_arg = ""
    font_path = FONTS_DIR / font_file
    if font_path.is_file():
        font_dir = tmp / "_fonts"
        font_dir.mkdir(exist_ok=True)
        shutil.copyfile(font_path, font_dir / font_path.name)
        fontsdir_arg = ":fontsdir='_fonts'"
    else:
        print(f"   ⚠ Font {font_path} not found — captions will use system font")

    # ── 4. Build xfade chain + subtitles ─────────────────────────────
    inputs: list[str] = []
    for i in range(n):
        inputs += ["-i", f"clip_{i + 1:02d}.mp4"]
    inputs += ["-i", str(audio_path.resolve())]

    use_music = BG_MUSIC_PATH.is_file()
    if use_music:
        inputs += ["-stream_loop", "-1", "-i", str(BG_MUSIC_PATH.resolve())]
    else:
        print(f"   ⚠ BGM {BG_MUSIC_PATH} not found — narration only")
    music_idx = n + 1

    filter_parts: list[str] = []

    if n == 1:
        filter_parts.append(f"[0:v]ass=captions.ass{fontsdir_arg}[final]")
    else:
        prev = "[0:v]"
        for i in range(n - 1):
            transition = XFADE_TRANSITIONS[i % len(XFADE_TRANSITIONS)]
            offset = (i + 1) * (clip_dur - FADE_DUR)
            next_v = f"[{i + 1}:v]"
            out = f"[x{i}]"
            filter_parts.append(
                f"{prev}{next_v}xfade=transition={transition}:"
                f"duration={FADE_DUR:.4f}:offset={offset:.4f}{out}"
            )
            prev = out
        filter_parts.append(f"{prev}ass=captions.ass{fontsdir_arg}[final]")

    dur_s = f"{total_duration:.3f}"
    if use_music:
        filter_parts.append(
            f"[{music_idx}:a]atrim=0:{dur_s},asetpts=PTS-STARTPTS,volume=0.20[_bgm]"
        )
        filter_parts.append(
            f"[{n}:a][_bgm]amix=inputs=2:weights='1 1':duration=first:normalize=0[audio_out]"
        )

    fc = ";\n".join(filter_parts)
    audio_map = "[audio_out]" if use_music else f"{n}:a"

    cmd = [
        "ffmpeg", "-y", "-hide_banner", "-loglevel", "warning",
        *inputs,
        "-filter_complex", fc,
        "-map", "[final]", "-map", audio_map,
        "-c:v", "libx264", "-preset", "fast", "-crf", "23",
        "-pix_fmt", "yuv420p",
        "-c:a", "aac", "-b:a", "192k",
        "-shortest",
        "-movflags", "+faststart",
        str(out_video.resolve()),
    ]
    subprocess.run(cmd, check=True, cwd=str(tmp), timeout=600)

    shutil.rmtree(tmp, ignore_errors=True)
