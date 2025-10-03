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
    fallback_start: float,
    fallback_end: float,
) -> Optional[Dict[str, object]]:
    if not chunk_words:
        return None

    start_raw = _coerce_time(chunk_words[0].get("start"))
    if start_raw is None or start_raw == 0.0:
        start = float(fallback_start)
    else:
        start = float(start_raw)

    end_raw = _coerce_time(chunk_words[-1].get("end"))
    if end_raw is None or end_raw <= start:
        end = float(max(fallback_end, start))
    else:
        end = float(end_raw)

    return {
        "start": round(start, 3),
        "end": round(end, 3),
        "text": _words_to_text(chunk_words),
        "probability": _average_probability(chunk_words),
        "words": [
            {
                "start": round(
                    float(_coerce_time(word.get("start")) or start),
                    3,
                ),
                "end": round(
                    float(
                        _coerce_time(word.get("end"))
                        or max(_coerce_time(word.get("start")) or start, end)
                    ),
                    3,
                ),
                "word": word.get("word", ""),
                "probability": round(float(word.get("probability")), 3)
                if word.get("probability") is not None
                else (
                    round(float(word.get("score")), 3)
                    if word.get("score") is not None
                    else None
                ),
            }
            for word in chunk_words
        ],
    }


def _segment_words(
    segment: Dict[str, object],
    thresholds: _Thresholds,
) -> List[Dict[str, object]]:
    words: List[Dict[str, object]] = list(segment.get("words") or [])

    previous_end = getattr(_segment_words, "_previous_end", 0.0)

    segment_start = _coerce_time(segment.get("start"))
    segment_end = _coerce_time(segment.get("end"))

    if segment_start is None or segment_start == 0.0:
        word_start = next(
            (
                _coerce_time(word.get("start"))
                for word in words
                if _coerce_time(word.get("start")) not in (None, 0.0)
            ),
            None,
        )
        if word_start not in (None, 0.0):
            segment_start = word_start

    if segment_start is None:
        segment_start = previous_end

    if segment_end is None or (
        segment_start is not None and segment_end <= segment_start
    ):
        word_end = next(
            (
                _coerce_time(word.get("end"))
                for word in reversed(words)
                if _coerce_time(word.get("end")) not in (None, 0.0)
            ),
            None,
        )
        if word_end not in (None, 0.0):
            segment_end = max(word_end, segment_start)

    if segment_end is None or segment_end < segment_start:
        segment_end = segment_start

    fallback_start = float(segment_start or 0.0)
    fallback_end = float(segment_end or fallback_start)

    if not words:
        text = segment.get("text", "").strip()
        if not text:
            _segment_words._previous_end = fallback_end
            return []
        chunk = {
            "start": round(fallback_start, 3),
            "end": round(fallback_end, 3),
            "text": text,
            "probability": segment.get("probability"),
            "words": [],
        }
        _segment_words._previous_end = fallback_end
        return [chunk]

    chunks: List[Dict[str, object]] = []
    current: List[Dict[str, object]] = []

    for word in words:
        normalized_word = _normalize_word(word)
        if _should_break_at_word(current, normalized_word, thresholds):
            chunk = _finalize_chunk(current, fallback_start, fallback_end)
            if chunk:
                chunks.append(chunk)
            current = [normalized_word]
        else:
            current.append(normalized_word)

    chunk = _finalize_chunk(current, fallback_start, fallback_end)
    if chunk:
        chunks.append(chunk)

    if len(chunks) == 1:
        single_chunk = chunks[0]
        rounded_start = round(fallback_start, 3)
        rounded_end = round(fallback_end, 3)

        single_chunk["start"] = rounded_start
        single_chunk["end"] = rounded_end

        for word in single_chunk.get("words", []):
            word["start"] = rounded_start
            word["end"] = rounded_end

        _segment_words._previous_end = fallback_end
        return chunks

    _segment_words._previous_end = fallback_end
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
