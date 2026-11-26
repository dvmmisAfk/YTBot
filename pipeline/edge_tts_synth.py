"""Edge TTS — free, no API key. Returns audio + sentence-level timestamps."""
from __future__ import annotations

import asyncio
import os
import subprocess
from pathlib import Path
from typing import TypedDict

import edge_tts

VOICE = "en-US-ChristopherNeural"


class SentenceTiming(TypedDict):
    text: str
    offset_ms: int
    duration_ms: int


def _ffprobe_duration(path: Path) -> float:
    out = subprocess.check_output(
        [
            "ffprobe", "-v", "error",
            "-show_entries", "format=duration",
            "-of", "default=noprint_wrappers=1:nokey=1",
            str(path),
        ],
        text=True,
    ).strip()
    return float(out)


async def _synthesize_with_timing(
    text: str, out_path: Path, voice: str,
) -> list[SentenceTiming]:
    communicate = edge_tts.Communicate(text, voice)
    sentences: list[SentenceTiming] = []

    with open(out_path, "wb") as audio_file:
        async for chunk in communicate.stream():
            if chunk["type"] == "audio":
                audio_file.write(chunk["data"])
            elif chunk["type"] == "SentenceBoundary":
                sentences.append(
                    SentenceTiming(
                        text=chunk["text"],
                        offset_ms=int(chunk["offset"]) // 10_000,
                        duration_ms=int(chunk["duration"]) // 10_000,
                    )
                )

    return sentences


class WordTiming(TypedDict):
    text: str
    start: float  # seconds
    end: float  # seconds
    sentence: int  # index of the sentence this word belongs to


async def _synthesize_words(text: str, out_path: Path, voice: str) -> list[dict]:
    communicate = edge_tts.Communicate(text, voice, boundary="WordBoundary")
    words: list[dict] = []
    with open(out_path, "wb") as audio_file:
        async for chunk in communicate.stream():
            if chunk["type"] == "audio":
                audio_file.write(chunk["data"])
            elif chunk["type"] == "WordBoundary":
                start = int(chunk["offset"]) / 10_000_000
                words.append(
                    {"text": chunk["text"], "start": start,
                     "end": start + int(chunk["duration"]) / 10_000_000}
                )
    return words


def _sentence_spans(text: str) -> list[tuple[int, int]]:
    import re

    spans = []
    for m in re.finditer(r"[^.!?]+(?:[.!?]+[\"'”’)]*|$)", text):
        if m.group().strip():
            spans.append((m.start(), m.end()))
    return spans or [(0, len(text))]


def synthesize_with_words(
    text: str, out_path: Path, voice: str | None = None,
) -> tuple[float, list[WordTiming], list[SentenceTiming]]:
    """TTS with word-level timings. Returns (duration_s, words, sentences).

    Each word is tagged with the index of its narration sentence, so callers can
    cut scenes on sentence boundaries and sync animation to individual words.
    """
    voice = voice or os.environ.get("EDGE_TTS_VOICE", VOICE)
    out_path = Path(out_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    raw = asyncio.run(_synthesize_words(text, out_path, voice))
    dur = _ffprobe_duration(out_path)

    spans = _sentence_spans(text)
    words: list[WordTiming] = []
    pos = 0
    for w in raw:
        found = text.find(w["text"], pos)
        if found >= 0:
            pos = found + len(w["text"])
        idx = next((i for i, (a, b) in enumerate(spans) if a <= max(found, pos - 1) < b), len(spans) - 1)
        words.append(WordTiming(text=w["text"], start=w["start"], end=w["end"], sentence=idx))

    sentences: list[SentenceTiming] = []
    for i, (a, b) in enumerate(spans):
        ws = [w for w in words if w["sentence"] == i]
        if not ws:
            continue
        sentences.append(SentenceTiming(
            text=text[a:b].strip(),
            offset_ms=int(ws[0]["start"] * 1000),
            duration_ms=int((ws[-1]["end"] - ws[0]["start"]) * 1000),
        ))
    return dur, words, sentences


def synthesize_full(
    text: str, out_path: Path, voice: str | None = None,
) -> tuple[float, list[SentenceTiming]]:
    """TTS the full narration. Returns (duration_seconds, sentence_timings)."""
    voice = voice or os.environ.get("EDGE_TTS_VOICE", VOICE)
    out_path = Path(out_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    sentences = asyncio.run(_synthesize_with_timing(text, out_path, voice))
    dur = _ffprobe_duration(out_path)
    return dur, sentences
