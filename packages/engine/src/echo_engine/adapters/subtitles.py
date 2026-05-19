from __future__ import annotations

from pathlib import Path

from echo_engine.domain.transcript import Transcript
from echo_engine.domain.translation import Translation


def _format_timestamp(seconds: float) -> str:
    hours = int(seconds // 3600)
    minutes = int((seconds % 3600) // 60)
    secs = int(seconds % 60)
    millis = int(round((seconds - int(seconds)) * 1000))
    if millis == 1000:
        secs += 1
        millis = 0
    return f"{hours:02d}:{minutes:02d}:{secs:02d},{millis:03d}"


def write_source_srt(transcript: Transcript, output_path: Path) -> Path:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    lines: list[str] = []
    index = 1
    for segment in transcript.segments:
        text = segment.text.strip()
        if not text:
            continue
        lines.extend([str(index), f"{_format_timestamp(segment.start)} --> {_format_timestamp(segment.end)}", text, ""])
        index += 1
    output_path.write_text("\n".join(lines), encoding="utf-8")
    return output_path


def write_translated_srt(translation: Translation, output_path: Path) -> Path:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    lines: list[str] = []
    index = 1
    for segment in translation.segments:
        text = segment.translated_text.strip()
        if not text:
            continue
        lines.extend([str(index), f"{_format_timestamp(segment.start)} --> {_format_timestamp(segment.end)}", text, ""])
        index += 1
    output_path.write_text("\n".join(lines), encoding="utf-8")
    return output_path


def write_bilingual_srt(translation: Translation, output_path: Path) -> Path:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    lines: list[str] = []
    index = 1
    for segment in translation.segments:
        source = segment.source_text.strip()
        translated = segment.translated_text.strip()
        if not source and not translated:
            continue
        lines.append(str(index))
        lines.append(f"{_format_timestamp(segment.start)} --> {_format_timestamp(segment.end)}")
        if source:
            lines.append(source)
        if translated:
            lines.append(translated)
        lines.append("")
        index += 1
    output_path.write_text("\n".join(lines), encoding="utf-8")
    return output_path
