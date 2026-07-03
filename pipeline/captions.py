"""Build caption files from Edge TTS sentence-level timestamps.

Splits each sentence into word groups (~5 words) and distributes
timing proportionally within the sentence's known time window.

Exports:
  build_srt  — legacy SRT (kept for reference)
  build_ass  — ASS/SSA with baked style for reliable ffmpeg positioning
"""
from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from pipeline.edge_tts_synth import SentenceTiming


# ── shared chunk builder ────────────────────────────────────────────────────

def _build_chunks(
    sentences: list,
    max_words_per_line: int,
) -> list[tuple[int, int, str]]:
    chunks: list[tuple[int, int, str]] = []
    for sent in sentences:
        words = sent["text"].split()
        if not words:
            continue
        start_ms = sent["offset_ms"]
        dur_ms = sent["duration_ms"]
        if len(words) <= max_words_per_line:
            chunks.append((start_ms, start_ms + dur_ms, sent["text"]))
        else:
            n_groups = (len(words) + max_words_per_line - 1) // max_words_per_line
            ms_per_word = dur_ms / len(words) if words else 1
            pos = 0
            for _ in range(n_groups):
                grp_end = min(pos + max_words_per_line, len(words))
                grp_text = " ".join(words[pos:grp_end])
                t_start = start_ms + int(pos * ms_per_word)
                t_end = min(start_ms + int(grp_end * ms_per_word), start_ms + dur_ms)
                chunks.append((t_start, t_end, grp_text))
                pos = grp_end
    return chunks


# ── SRT ────────────────────────────────────────────────────────────────────

def _srt_ts(ms: int) -> str:
    h = ms // 3_600_000
    m = (ms % 3_600_000) // 60_000
    s = (ms % 60_000) // 1_000
    frac = ms % 1_000
    return f"{h:02d}:{m:02d}:{s:02d},{frac:03d}"


def build_srt(
    sentences: list,
    out_path: Path,
    total_duration: float,
    *,
    max_words_per_line: int = 5,
) -> Path:
    out_path = Path(out_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    if not sentences:
        out_path.write_text("", encoding="utf-8")
        return out_path
    chunks = _build_chunks(sentences, max_words_per_line)
    lines: list[str] = []
    for i, (start, end, text) in enumerate(chunks):
        lines += [str(i + 1), f"{_srt_ts(start)} --> {_srt_ts(end)}", text, ""]
    out_path.write_text("\n".join(lines), encoding="utf-8")
    return out_path


# ── ASS ────────────────────────────────────────────────────────────────────

def _ass_ts(ms: int) -> str:
    h = ms // 3_600_000
    m = (ms % 3_600_000) // 60_000
    s = (ms % 60_000) // 1_000
    cs = (ms % 1_000) // 10
    return f"{h}:{m:02d}:{s:02d}.{cs:02d}"


def caption_margin_for_image(
    image_width: int,
    image_height: int,
    *,
    play_res_x: int = 1080,
    play_res_y: int = 1920,
    padding: int = 48,
) -> int:
    """ASS MarginV for bottom-aligned captions sitting on the image footer.

    Images are scaled with force_original_aspect_ratio=decrease and letterboxed
    to the canvas; this places text just above the bottom black bar.
    """
    scale = min(play_res_x / max(image_width, 1), play_res_y / max(image_height, 1))
    scaled_h = image_height * scale
    bottom_bar = (play_res_y - scaled_h) / 2
    return int(bottom_bar + padding)


def build_ass(
    sentences: list,
    out_path: Path,
    total_duration: float,
    *,
    max_words_per_line: int = 5,
    font_name: str = "Arial",
    font_size: int = 58,
    play_res_x: int = 1080,
    play_res_y: int = 1920,
    margin_v: int | None = None,
    image_width: int | None = None,
    image_height: int | None = None,
) -> Path:
    """Generate an ASS subtitle file with bottom-center alignment baked into the style.

    Using ASS instead of SRT + force_style guarantees that Alignment=2
    (bottom-center) and MarginV are honoured across all ffmpeg versions.

    Font size is in output pixels (PlayResX/Y match the render resolution)
    so font_size=58 → 58px tall glyphs on a 1920-tall canvas (~3 % of height).

    ASS colour format: &HAABBGGRR
      white text  → &H00FFFFFF
      gold outline → &H0000AAFF  (alpha=00, blue=00, green=AA, red=FF)
      semi-black box   → &H80000000  (alpha=80 = 50% transparent)
    """
    out_path = Path(out_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)

    if margin_v is None:
        if image_width and image_height:
            margin_v = caption_margin_for_image(image_width, image_height)
        else:
            margin_v = 180

    if not sentences:
        out_path.write_text("", encoding="utf-8")
        return out_path

    chunks = _build_chunks(sentences, max_words_per_line)

    header = (
        "[Script Info]\n"
        "ScriptType: v4.00+\n"
        f"PlayResX: {play_res_x}\n"
        f"PlayResY: {play_res_y}\n"
        "WrapStyle: 0\n"
        "\n"
        "[V4+ Styles]\n"
        "Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, "
        "OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, "
        "ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, "
        "Alignment, MarginL, MarginR, MarginV, Encoding\n"
        f"Style: Default,{font_name},{font_size},"
        "&H00FFFFFF,&H00FFFFFF,&H0000AAFF,&H80000000,"  # colours
        "-1,0,0,0,100,100,0,0,"                          # Bold, no italic/underline
        f"4,3,0,"                                         # BorderStyle=4 (box), Outline=3
        f"2,20,20,{margin_v},1\n"                        # Alignment=2 bottom-center
        "\n"
        "[Events]\n"
        "Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text\n"
    )

    events = [
        f"Dialogue: 0,{_ass_ts(s)},{_ass_ts(e)},Default,,0,0,0,,{text}"
        for s, e, text in chunks
    ]

    out_path.write_text(header + "\n".join(events) + "\n", encoding="utf-8")
    return out_path
