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

    def min_words_for_punctuation(self) -> int:
        if self.max_words:
            return max(3, self.max_words // 2)
        return 12

    def min_chars_for_punctuation(self) -> int:
        if self.max_chars:
            return max(20, self.max_chars // 2)
        return 60

    def allow_punctuation_split(self, segment_words: int, segment_chars: int) -> bool:
        return (
            segment_words >= self.min_words_for_punctuation()
            or segment_chars >= self.min_chars_for_punctuation()
        )


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

    if not thresholds.allow_punctuation_split(
        segment_words=len(current),
        segment_chars=len(_words_to_text(current)),
    ):
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

    start = float(chunk_words[0].get("start", fallback_start))
    end = float(chunk_words[-1].get("end", fallback_end))

    return {
        "start": round(start, 3),
        "end": round(end, 3),
        "text": _words_to_text(chunk_words),
        "probability": _average_probability(chunk_words),
        "words": [
            {
                "start": round(float(word.get("start", start)), 3),
                "end": round(float(word.get("end", end)), 3),
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
    if not words:
        text = segment.get("text", "").strip()
        if not text:
            return []
        start = float(segment.get("start", 0.0))
        end = float(segment.get("end", start))
        return [
            {
                "start": round(start, 3),
                "end": round(end, 3),
                "text": text,
                "probability": segment.get("probability"),
                "words": [],
            }
        ]

    chunks: List[Dict[str, object]] = []
    current: List[Dict[str, object]] = []

    for word in words:
        normalized_word = _normalize_word(word)
        if _should_break_at_word(current, normalized_word, thresholds):
            chunk = _finalize_chunk(current, segment.get("start", 0.0), segment.get("end", 0.0))
            if chunk:
                chunks.append(chunk)
            current = [normalized_word]
        else:
            current.append(normalized_word)

    chunk = _finalize_chunk(current, segment.get("start", 0.0), segment.get("end", 0.0))
    if chunk:
        chunks.append(chunk)

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
