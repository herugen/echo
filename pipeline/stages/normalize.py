"""Normalize transcription timestamps prior to segmentation."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Tuple

from ..config import PipelineConfig
from ..context import PipelineContext

_ROUND_PLACES = 3


def _coerce_time(value: object) -> Optional[float]:
    if value is None:
        return None
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    if number < 0:
        return None
    return number


def _round_time(value: float) -> float:
    return round(float(value), _ROUND_PLACES)


def _first_valid(values: Iterable[Optional[float]]) -> Optional[float]:
    for candidate in values:
        if candidate is not None:
            return candidate
    return None


def _normalize_words(
    words: List[Dict[str, object]],
    segment_start: float,
    segment_end: float,
) -> Tuple[List[Dict[str, object]], float, int]:
    normalized: List[Dict[str, object]] = []
    fixes = 0
    cursor = segment_start

    for original in words:
        word_copy = dict(original)

        start_value = _coerce_time(original.get("start"))
        if start_value is None or start_value < cursor:
            start_value = cursor
            fixes += 1

        end_value = _coerce_time(original.get("end"))
        if end_value is None or end_value < start_value:
            end_value = start_value
            fixes += 1

        if end_value > segment_end:
            end_value = segment_end
            fixes += 1

        cursor = end_value

        word_copy["start"] = _round_time(start_value)
        word_copy["end"] = _round_time(end_value)
        normalized.append(word_copy)

    if normalized:
        cursor = max(cursor, normalized[-1]["end"])

    return normalized, cursor, fixes


def _normalize_segment(
    segment: Dict[str, object],
    previous_end: float,
) -> Tuple[Dict[str, object], float, int, int]:
    words: List[Dict[str, object]] = list(segment.get("words") or [])

    explicit_start = _coerce_time(segment.get("start"))
    explicit_end = _coerce_time(segment.get("end"))

    word_starts = [_coerce_time(word.get("start")) for word in words]
    word_ends = [_coerce_time(word.get("end")) for word in words]

    segment_start = _first_valid(
        (
            explicit_start,
            _first_valid(word_starts),
            previous_end,
        )
    )
    if segment_start is None:
        segment_start = previous_end

    if segment_start < previous_end:
        segment_start = previous_end

    segment_end = _first_valid(
        (
            explicit_end,
            next((value for value in reversed(word_ends) if value is not None), None),
            segment_start,
        )
    )
    if segment_end is None:
        segment_end = segment_start

    if segment_end < segment_start:
        segment_end = segment_start

    segment_fix = 0
    if explicit_start is None or explicit_start != segment_start:
        segment_fix += 1
    if explicit_end is None or explicit_end != segment_end:
        segment_fix += 1

    normalized_words, last_word_end, word_fixes = _normalize_words(words, segment_start, segment_end)

    if normalized_words:
        segment_end = max(segment_end, float(normalized_words[-1]["end"]))
    else:
        segment_end = segment_start

    normalized_segment = dict(segment)
    normalized_segment["start"] = _round_time(segment_start)
    normalized_segment["end"] = _round_time(segment_end)
    normalized_segment["words"] = normalized_words

    return normalized_segment, segment_end, segment_fix, word_fixes


def normalize_transcript(
    transcript: Dict[str, object],
    config: PipelineConfig,
    context: PipelineContext,
) -> Tuple[Dict[str, object], Path]:
    """Normalize transcript timestamps and persist the cleaned version."""

    del config  # Unused, but kept for signature consistency

    segments = list(transcript.get("segments") or [])
    normalized_segments: List[Dict[str, object]] = []

    previous_end = 0.0
    segment_fixes = 0
    word_fixes = 0

    for segment in segments:
        normalized_segment, previous_end, seg_fix, word_fix = _normalize_segment(segment, previous_end)
        normalized_segments.append(normalized_segment)
        segment_fixes += seg_fix
        word_fixes += word_fix

    total_duration = transcript.get("total_duration")
    total_duration_value = _coerce_time(total_duration)
    if normalized_segments:
        inferred_duration = float(normalized_segments[-1]["end"])
        if total_duration_value is None or total_duration_value < inferred_duration:
            total_duration_value = inferred_duration
    else:
        total_duration_value = total_duration_value or 0.0

    normalized_transcript: Dict[str, object] = {
        "language": transcript.get("language"),
        "segments": normalized_segments,
        "total_segments": len(normalized_segments),
        "total_duration": _round_time(total_duration_value or 0.0),
        "stats": {
            "segment_fixes": segment_fixes,
            "word_fixes": word_fixes,
        },
    }

    output_path = context.subpath("transcripts", "transcript.normalized.json")
    with output_path.open("w", encoding="utf-8") as fp:
        json.dump(normalized_transcript, fp, ensure_ascii=False, indent=2)

    return normalized_transcript, output_path

