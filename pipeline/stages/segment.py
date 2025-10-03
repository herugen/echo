"""Segment transcription results into shorter, subtitle-friendly chunks."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Tuple

from ..config import PipelineConfig
from ..context import PipelineContext

_MAJOR_PUNCTUATION = {".", "!", "?", "。", "！", "？"}
_MINOR_PUNCTUATION = {",", ";", ":", "，", "；", "："}


@dataclass
class _Thresholds:
    max_words: int
    max_chars: int

    @classmethod
    def from_config(cls, config: PipelineConfig) -> "_Thresholds":
        return cls(
            max_words=max(config.whisper_segment_max_words or 0, 0),
            max_chars=max(config.whisper_segment_max_chars or 0, 0),
        )

    def exceeds(self, words: List[Dict[str, object]], candidate: Dict[str, object]) -> bool:
        if not words:
            return False

        future_words = words + [candidate]
        if self.max_words and len(future_words) > self.max_words:
            return True

        if self.max_chars:
            text = _words_to_text(future_words)
            if len(text) > self.max_chars:
                return True

        return False


def _coerce_time(value: object) -> Optional[float]:
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _words_to_text(words: Iterable[Dict[str, object]]) -> str:
    raw = " ".join(word.get("word", "").strip() for word in words)
    return " ".join(raw.split())


def _average_probability(words: Iterable[Dict[str, object]]) -> Optional[float]:
    scores: List[float] = []
    for word in words:
        prob = word.get("probability")
        if prob is None and word.get("score") is not None:
            prob = word["score"]
        if prob is None:
            continue
        try:
            scores.append(float(prob))
        except (TypeError, ValueError):
            continue
    if not scores:
        return None
    return round(sum(scores) / len(scores), 3)


def _normalize_word(word: Dict[str, object]) -> Dict[str, object]:
    normalized = dict(word)
    normalized_word = word.get("word", "")
    normalized_word = normalized_word.strip()
    normalized["word"] = normalized_word
    normalized["suffix"] = normalized_word[-1] if normalized_word else ""
    return normalized


def _is_major_boundary(word: Dict[str, object]) -> bool:
    suffix = word.get("suffix", "")
    return suffix in _MAJOR_PUNCTUATION


def _is_minor_boundary(word: Dict[str, object]) -> bool:
    suffix = word.get("suffix", "")
    return suffix in _MINOR_PUNCTUATION


def _should_break_at_word(
    current: List[Dict[str, object]],
    candidate: Dict[str, object],
    thresholds: _Thresholds,
) -> bool:
    if thresholds.exceeds(current, candidate):
        return True

    if not current:
        return False

    if _is_major_boundary(current[-1]):
        return True

    if _is_minor_boundary(current[-1]) and _is_minor_boundary(candidate):
        return True

    return False


def _finalize_chunk(
    chunk_words: List[Dict[str, object]],
) -> Dict[str, object]:
    if not chunk_words:
        raise ValueError("Cannot finalize an empty chunk; expected at least one word.")

    start_raw = _coerce_time(chunk_words[0].get("start"))
    end_raw = _coerce_time(chunk_words[-1].get("end"))

    if start_raw is None or end_raw is None:
        raise ValueError("Word timestamps must be present after normalization.")
    if end_raw < start_raw:
        raise ValueError("Word timestamps are not monotonically increasing.")

    start = float(start_raw)
    end = float(end_raw)

    words_payload: List[Dict[str, object]] = []
    last_end = start

    for word in chunk_words:
        word_start = _coerce_time(word.get("start"))
        word_end = _coerce_time(word.get("end"))
        if word_start is None or word_end is None:
            raise ValueError("Word timestamps must be present after normalization.")
        if word_end < word_start:
            raise ValueError("Encountered a word with end earlier than start.")
        if word_start < last_end:
            raise ValueError("Word timestamps are not monotonically increasing.")
        last_end = word_end

        words_payload.append(
            {
                "start": round(word_start, 3),
                "end": round(word_end, 3),
                "word": word.get("word", ""),
                "probability": round(float(word.get("probability")), 3)
                if word.get("probability") is not None
                else (
                    round(float(word.get("score")), 3)
                    if word.get("score") is not None
                    else None
                ),
            }
        )

    return {
        "start": round(start, 3),
        "end": round(end, 3),
        "text": _words_to_text(chunk_words),
        "probability": _average_probability(chunk_words),
        "words": words_payload,
    }


def _segment_words(
    segment: Dict[str, object],
    thresholds: _Thresholds,
) -> List[Dict[str, object]]:
    words: List[Dict[str, object]] = list(segment.get("words") or [])

    previous_end = getattr(_segment_words, "_previous_end", 0.0)

    segment_start = _coerce_time(segment.get("start"))
    segment_end = _coerce_time(segment.get("end"))

    if segment_start is None or segment_end is None:
        raise ValueError("Segment timestamps must be present after normalization.")
    if segment_end < segment_start:
        raise ValueError("Segment end timestamp is earlier than start.")
    if segment_start < previous_end:
        raise ValueError("Segment timestamps regress compared to the previous segment.")

    if not words:
        text = segment.get("text", "").strip()
        if not text:
            _segment_words._previous_end = float(segment_end)
            return []
        chunk = {
            "start": round(float(segment_start), 3),
            "end": round(float(segment_end), 3),
            "text": text,
            "probability": segment.get("probability"),
            "words": [],
        }
        _segment_words._previous_end = float(segment_end)
        return [chunk]

    chunks: List[Dict[str, object]] = []
    current: List[Dict[str, object]] = []

    for word in words:
        normalized_word = _normalize_word(word)
        if _should_break_at_word(current, normalized_word, thresholds):
            chunks.append(_finalize_chunk(current))
            current = [normalized_word]
        else:
            current.append(normalized_word)

    chunks.append(_finalize_chunk(current))

    _segment_words._previous_end = float(segment_end)
    return chunks


def split_transcript_segments(
    transcript: Dict[str, object],
    config: PipelineConfig,
    context: PipelineContext,
) -> Tuple[Dict[str, object], Path]:
    """Split WhisperX output into shorter segments based on configuration."""

    thresholds = _Thresholds.from_config(config)
    segmented: List[Dict[str, object]] = []

    for segment in transcript.get("segments", []):
        segmented.extend(_segment_words(segment, thresholds))

    total_duration = (
        round(segmented[-1]["end"], 3) if segmented else transcript.get("total_duration", 0.0)
    )

    result: Dict[str, object] = {
        "language": transcript.get("language", "unknown"),
        "segments": segmented,
        "total_segments": len(segmented),
        "total_duration": total_duration,
    }

    output_path = context.subpath("transcripts", "segments.json")
    with output_path.open("w", encoding="utf-8") as fp:
        json.dump(result, fp, ensure_ascii=False, indent=2)

    return result, output_path
