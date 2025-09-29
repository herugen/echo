"""Subtitle generation stages."""

from __future__ import annotations

from pathlib import Path
from typing import Dict, List

from ..context import PipelineContext


def _format_timestamp(seconds: float) -> str:
    hours = int(seconds // 3600)
    minutes = int((seconds % 3600) // 60)
    secs = int(seconds % 60)
    milliseconds = int((seconds % 1) * 1000)
    return f"{hours:02d}:{minutes:02d}:{secs:02d},{milliseconds:03d}"


def generate_source_subtitles(segments: List[Dict], context: PipelineContext) -> Path:
    path = context.subpath("transcripts", "source.srt")
    _write_segments_to_srt(segments, path)
    return path


def generate_translated_subtitles(segments: List[Dict], context: PipelineContext) -> Path:
    path = context.subpath("translations", "translated.srt")
    _write_segments_to_srt(segments, path)
    return path


def _write_segments_to_srt(segments: List[Dict], path: Path) -> None:
    lines = []
    index = 1
    for segment in segments:
        text = segment.get("text", "").strip()
        if not text:
            continue
        start = _format_timestamp(segment["start"])
        end = _format_timestamp(segment["end"])
        lines.extend([str(index), f"{start} --> {end}", text, ""])
        index += 1
    with path.open("w", encoding="utf-8") as fp:
        fp.write("\n".join(lines))

