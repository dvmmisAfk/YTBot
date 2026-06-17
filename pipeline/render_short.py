"""FFmpeg: images + audio + captions → vertical Short MP4 (9:16).

Horror effects stack:
  - Ken Burns zoom (alternating zoom-in / zoom-out, 10% range for drama)
  - Cycling horror xfade transitions: fadeblack → distance → fadegrays → dissolve → zoomin
  - Color grading: desaturated, darkened, contrast-boosted for cold horror look
  - Vignette: dark edges that focus the eye and add cinematic dread
  - Eerie ambient audio: low sine drone + filtered pink noise + reverb, mixed under narration at 15%
  - Creepster font captions with red outline at the bottom
"""
from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
FONTS_DIR = REPO_ROOT / "assets" / "fonts"
DEFAULT_FONT_FILE = "CreepsterCaps.ttf"
DEFAULT_FONT_NAME = "Creepster"

FPS = 30
FADE_DUR = 0.5
ZOOM_AMOUNT = 0.10  # 10% zoom range — more dramatic than default 8%

# Cycling horror xfade transitions for scene variety
HORROR_XFADE_TRANSITIONS = [
    "fadeblack",   # fade through black (primary horror transition)
    "distance",    # eerie wave-distortion warp
    "fadegrays",   # desaturate during transition — ghostly
    "fadeblack",
    "dissolve",    # ghostly pixel dissolve
    "zoomin",      # punch-zoom into next scene
    "fadeblack",
]


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

    # ── 2. Generate zoompan clips ────────────────────────────────────
    for i in range(n):
        src_img = tmp / f"img_{i + 1:02d}.png"
        clip = tmp / f"clip_{i + 1:02d}.mp4"
        zoom_rate = ZOOM_AMOUNT / frames_per_clip

        if i % 2 == 0:
            zoom_expr = f"min(zoom+{zoom_rate:.8f},{1 + ZOOM_AMOUNT})"
        else:
            zoom_expr = f"if(eq(on,1),{1 + ZOOM_AMOUNT},max(zoom-{zoom_rate:.8f},1.0))"

        vf = (
            f"zoompan=z='{zoom_expr}':"
            f"x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)':"
            f"d={frames_per_clip}:s={width}x{height}:fps={FPS},"
            f"format=yuv420p"
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

    # White text, red outline, semi-transparent dark box — horror aesthetic
    # ASS color format: &HAABBGGRR (alpha, blue, green, red)
    force_style = (
        f"FontName={rendered_font_name},"
        f"FontSize=20,"
        f"PrimaryColour=&H00FFFFFF,"
        f"OutlineColour=&H000000BB,"
        f"BackColour=&H80000000,"
        f"BorderStyle=4,Outline=2,Bold=1,"
        f"Shadow=0,Alignment=2,"
        f"MarginV=30,MarginL=20,MarginR=20"
    )

    # ── 4. Build xfade chain + horror grade + vignette + subtitles ───
    inputs: list[str] = []
    for i in range(n):
        inputs += ["-i", f"clip_{i + 1:02d}.mp4"]
    inputs += ["-i", str(audio_path.resolve())]

    filter_parts: list[str] = []

    if n == 1:
        filter_parts.append(
            "[0:v]eq=saturation=0.72:brightness=-0.04:contrast=1.10[_grade]"
        )
        filter_parts.append("[_grade]vignette=PI/3.5[_vig]")
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
        # Apply horror color grade and vignette once on the composited video
        filter_parts.append(
            f"{prev}eq=saturation=0.72:brightness=-0.04:contrast=1.10[_grade]"
        )
        filter_parts.append("[_grade]vignette=PI/3.5[_vig]")
        filter_parts.append(
            f"[_vig]subtitles=captions.srt{fontsdir_arg}:"
            f"force_style='{force_style}'[final]"
        )

    # ── Eerie ambient audio ───────────────────────────────────────────
    # Low sine drone (55 Hz + 75 Hz + 100 Hz) + filtered pink noise, reverbed,
    # mixed under the narration at 15% volume for atmospheric horror dread.
    dur_s = f"{total_duration:.3f}"
    filter_parts.append(
        f"aevalsrc=sin(2*PI*55*t)*0.06+sin(2*PI*75*t)*0.04+sin(2*PI*100*t)*0.02:"
        f"c=mono:r=44100:d={dur_s}[_drone]"
    )
    filter_parts.append(f"anoisesrc=d={dur_s}:c=pink:a=0.025[_noise]")
    filter_parts.append("[_noise]lowpass=f=280[_wind]")
    filter_parts.append("[_drone][_wind]amix=inputs=2:weights='1 0.5'[_ambient_raw]")
    filter_parts.append("[_ambient_raw]aecho=0.70:0.80:300:0.4[_ambient]")
    filter_parts.append(
        f"[{n}:a][_ambient]amix=inputs=2:weights='1 0.15':duration=first[audio_out]"
    )

    fc = ";\n".join(filter_parts)

    cmd = [
        "ffmpeg", "-y", "-hide_banner", "-loglevel", "warning",
        *inputs,
        "-filter_complex", fc,
        "-map", "[final]", "-map", "[audio_out]",
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
