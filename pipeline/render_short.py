"""FFmpeg: images + audio + captions → vertical Short MP4 (9:16).

Horror effects stack:
  - Ken Burns zoom (alternating zoom-in / zoom-out, 10% range for drama)
  - Cycling horror xfade transitions: fadeblack → distance → fadegrays → dissolve → zoomin
  - Dynamic per-video color palette: randomly chosen from 5 distinct horror grades
  - Per-scene intensity ramp: clips darken toward climax, contrast peaks mid-story
  - Randomised vignette angle for subtle variety across videos
  - Background music: subterranean-machinery.mp3 looped at 20% under narration
  - Creepster font captions: top-center with 80 px top gap for easy reading
"""
from __future__ import annotations

import random
import shutil
import subprocess
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
FONTS_DIR = REPO_ROOT / "assets" / "fonts"
BG_MUSIC_PATH = REPO_ROOT / "subterranean-machinery.mp3"
DEFAULT_FONT_FILE = "CreepsterCaps.ttf"
DEFAULT_FONT_NAME = "Creepster"

FPS = 30
FADE_DUR = 0.5
ZOOM_AMOUNT = 0.10

# Cycling horror xfade transitions for scene variety
HORROR_XFADE_TRANSITIONS = [
    "fadeblack",
    "distance",
    "fadegrays",
    "fadeblack",
    "dissolve",
    "zoomin",
    "fadeblack",
]

# Five distinct horror color palettes — one is randomly selected per video
# so every video has a different visual identity
COLOR_PALETTES = [
    # cold blue: frozen ghost dread
    {"sat": 0.55, "bright": -0.06, "contrast": 1.20,
     "extra": "colorchannelmixer=rr=0.85:gg=0.95:bb=1.15"},
    # sickly green: rotting, infection, swamp
    {"sat": 0.60, "bright": -0.05, "contrast": 1.15,
     "extra": "colorchannelmixer=rr=0.90:gg=1.10:bb=0.85"},
    # deep shadow: psychological crushing darkness
    {"sat": 0.45, "bright": -0.10, "contrast": 1.32,
     "extra": ""},
    # crimson noir: blood-tinted shadows, lurking danger
    {"sat": 0.50, "bright": -0.08, "contrast": 1.25,
     "extra": "colorchannelmixer=rr=1.15:gg=0.90:bb=0.85"},
    # ashen fog: ghostly pale, barely there
    {"sat": 0.35, "bright": -0.03, "contrast": 1.08,
     "extra": "colorchannelmixer=rr=0.95:gg=0.97:bb=1.05"},
]

VIGNETTE_ANGLES = ["PI/3.5", "PI/4", "PI/3", "PI/2.8"]


def _clip_grade_vf(idx: int, n: int, palette: dict) -> str:
    """Per-clip color grade that varies with narrative position.

    Opens at the palette's base values, darkens toward the climax scene,
    and slightly brightens the final frame for a cold landing.
    """
    progress = idx / max(n - 1, 1)  # 0.0 at first clip, 1.0 at last
    # Darken progressively through the first 65% of the story
    dark_ramp = min(progress / 0.65, 1.0) * -0.05
    # Contrast boost peaks in the middle (rising action through climax)
    contrast_bump = 0.12 if 0.25 < progress < 0.85 else 0.0

    b = palette["bright"] + dark_ramp
    c = palette["contrast"] + contrast_bump
    vf = f"eq=saturation={palette['sat']:.2f}:brightness={b:.3f}:contrast={c:.2f}"
    if palette.get("extra"):
        vf += f",{palette['extra']}"
    return vf


def render_vertical_short(
    image_paths: list[Path],
    total_duration: float,
    audio_path: Path,
    srt_path: Path,
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

    # Pick random visual identity for this video
    palette = random.choice(COLOR_PALETTES)
    vignette_angle = random.choice(VIGNETTE_ANGLES)

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
    shutil.copyfile(srt_path, tmp / "captions.srt")

    font_path = FONTS_DIR / font_file
    rendered_font_name = "Arial"
    fontsdir_arg = ""
    if font_path.is_file():
        font_dir = tmp / "_fonts"
        font_dir.mkdir(exist_ok=True)
        shutil.copyfile(font_path, font_dir / font_path.name)
        rendered_font_name = font_name
        fontsdir_arg = ":fontsdir='_fonts'"
    else:
        print(f"   ⚠ Font {font_path} not found — using {rendered_font_name}")

    # Top-center captions: Alignment=8 (ASS numpad top-center), MarginV=80 (top gap)
    force_style = (
        f"FontName={rendered_font_name},"
        f"FontSize=22,"
        f"PrimaryColour=&H00FFFFFF,"
        f"OutlineColour=&H000000BB,"
        f"BackColour=&H80000000,"
        f"BorderStyle=4,Outline=3,Bold=1,"
        f"Shadow=0,Alignment=8,"
        f"MarginV=80,MarginL=20,MarginR=20"
    )

    # ── 4. Build xfade chain + vignette + subtitles ───────────────────
    inputs: list[str] = []
    for i in range(n):
        inputs += ["-i", f"clip_{i + 1:02d}.mp4"]
    inputs += ["-i", str(audio_path.resolve())]

    use_music = BG_MUSIC_PATH.is_file()
    if use_music:
        # -stream_loop -1 must appear before its -i to loop the file
        inputs += ["-stream_loop", "-1", "-i", str(BG_MUSIC_PATH.resolve())]
    music_idx = n + 1  # clips 0..n-1, narration n, music n+1

    filter_parts: list[str] = []

    if n == 1:
        filter_parts.append(f"[0:v]vignette={vignette_angle}[_vig]")
        filter_parts.append(
            f"[_vig]subtitles=captions.srt{fontsdir_arg}:"
            f"force_style='{force_style}'[final]"
        )
    else:
        prev = "[0:v]"
        for i in range(n - 1):
            transition = HORROR_XFADE_TRANSITIONS[i % len(HORROR_XFADE_TRANSITIONS)]
            offset = (i + 1) * (clip_dur - FADE_DUR)
            next_v = f"[{i + 1}:v]"
            out = f"[x{i}]"
            filter_parts.append(
                f"{prev}{next_v}xfade=transition={transition}:"
                f"duration={FADE_DUR:.4f}:offset={offset:.4f}{out}"
            )
            prev = out
        filter_parts.append(f"{prev}vignette={vignette_angle}[_vig]")
        filter_parts.append(
            f"[_vig]subtitles=captions.srt{fontsdir_arg}:"
            f"force_style='{force_style}'[final]"
        )

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

    # ── cleanup ──────────────────────────────────────────────────────
    shutil.rmtree(tmp, ignore_errors=True)
