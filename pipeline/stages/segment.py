"""Segment transcription results into subtitle-friendly chunks using rule-based scoring."""

from __future__ import annotations

import json
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Sequence, Tuple

from ..config import PipelineConfig
from ..context import PipelineContext

_MAJOR_PUNCTUATION = {".", "!", "?", "。", "！", "？"}
_MINOR_PUNCTUATION = {",", ";", ":", "，", "；", "："}
_OPEN_WITHOUT_SPACE = {"\"", "'", "“", "‘", "("}
_CLOSING_WITHOUT_SPACE = {".", ",", "!", "?", ":", ";", "”", "’", "'", "\"", ")"}
_SOFT_CONNECTORS = {
    "and",
    "but",
    "or",
    "so",
    "because",
    "that",
    "which",
    "who",
    "when",
    "where",
    "while",
    "if",
    "then",
    "though",
    "although",
    "however",
    "therefore",
}


@dataclass
class _SubtitleConstraints:
    max_chars: int
    min_duration: float
    max_duration: float
    max_chars_per_second: float
    preferred_chars: int
    preferred_duration: float
    pause_strong: float
    pause_weak: float
    pause_soft: float
    break_penalty: float

    @classmethod
    def from_config(cls, config: PipelineConfig) -> "_SubtitleConstraints":
        return cls(
            max_chars=max(config.subtitle_max_chars, 1),
            min_duration=max(config.subtitle_min_duration, 0.1),
            max_duration=max(config.subtitle_max_duration, config.subtitle_min_duration + 0.1),
            max_chars_per_second=max(config.subtitle_max_chars_per_second, 1.0),
            preferred_chars=max(config.subtitle_preferred_chars, 1),
            preferred_duration=max(config.subtitle_preferred_duration, config.subtitle_min_duration),
            pause_strong=max(config.subtitle_pause_strong, 0.0),
            pause_weak=max(config.subtitle_pause_weak, 0.0),
            pause_soft=max(config.subtitle_pause_soft, 0.0),
            break_penalty=max(config.subtitle_break_penalty, 0.0),
        )


def _coerce_time(value: object) -> Optional[float]:
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _words_to_text(words: Iterable[Dict[str, object]]) -> str:
    buffer: List[str] = []
    for word in words:
        token = str(word.get("word", ""))
        if not token:
            continue
        cleaned = token.strip()
        if not cleaned:
            continue
        if buffer and cleaned[:1] in _CLOSING_WITHOUT_SPACE:
            buffer[-1] = buffer[-1] + cleaned
        elif buffer and buffer[-1][-1:] in _OPEN_WITHOUT_SPACE:
            buffer[-1] = buffer[-1] + cleaned
        elif cleaned[:1] in _OPEN_WITHOUT_SPACE:
            buffer.append(buffer.pop() + cleaned if buffer else cleaned)
        else:
            buffer.append(cleaned)
    return " ".join(buffer)


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
    normalized["prefix"] = normalized_word[:1] if normalized_word else ""
    return normalized


def _duration(words: Sequence[Dict[str, object]]) -> float:
    if not words:
        return 0.0
    start = _coerce_time(words[0].get("start"))
    end = _coerce_time(words[-1].get("end"))
    if start is None or end is None:
        return 0.0
    return max(end - start, 0.0)


def _chars(words: Sequence[Dict[str, object]]) -> int:
    return len(_words_to_text(words))


def _chars_per_second(words: Sequence[Dict[str, object]]) -> float:
    dur = _duration(words)
    if dur <= 0:
        return float("inf")
    return _chars(words) / dur


def _gap(prev: Dict[str, object], nxt: Dict[str, object]) -> float:
    prev_end = _coerce_time(prev.get("end"))
    next_start = _coerce_time(nxt.get("start"))
    if prev_end is None or next_start is None:
        return 0.0
    return max(next_start - prev_end, 0.0)


def _pause_score(gap: float, constraints: _SubtitleConstraints) -> float:
    if gap >= constraints.pause_strong:
        return 1.0
    if gap >= constraints.pause_weak:
        return 0.6
    if gap >= constraints.pause_soft:
        return 0.25
    return 0.0


def _punctuation_score(word: Dict[str, object]) -> float:
    suffix = word.get("suffix", "")
    if suffix in _MAJOR_PUNCTUATION:
        return 1.0
    if suffix in _MINOR_PUNCTUATION:
        return 0.5
    return 0.0


def _connector_penalty(word: Dict[str, object]) -> float:
    token = word.get("word", "").lower()
    if token in _SOFT_CONNECTORS:
        return 0.4
    return 0.0


def _length_preference(words: Sequence[Dict[str, object]], constraints: _SubtitleConstraints) -> float:
    chars = _chars(words)
    if chars > constraints.max_chars:
        return -1.0
    diff = abs(chars - constraints.preferred_chars) / constraints.preferred_chars
    return max(0.0, 0.6 - diff)


def _duration_preference(words: Sequence[Dict[str, object]], constraints: _SubtitleConstraints) -> float:
    dur = _duration(words)
    if dur < constraints.min_duration or dur > constraints.max_duration:
        return -1.0
    diff = abs(dur - constraints.preferred_duration) / max(constraints.preferred_duration, 0.1)
    return max(0.0, 0.6 - diff)


def _reading_speed_penalty(words: Sequence[Dict[str, object]], constraints: _SubtitleConstraints) -> float:
    cps = _chars_per_second(words)
    if cps <= constraints.max_chars_per_second:
        diff = (constraints.max_chars_per_second - cps) / constraints.max_chars_per_second
        return max(0.0, 0.5 * diff)
    diff = (cps - constraints.max_chars_per_second) / constraints.max_chars_per_second
    return -1.5 * min(diff, 1.0)


def _chunk_score(
    words: Sequence[Dict[str, object]],
    constraints: _SubtitleConstraints,
    lead_gap: float,
    tail_gap: float,
) -> float:
    if not words:
        return float("-inf")

    length_score = _length_preference(words, constraints)
    duration_score = _duration_preference(words, constraints)
    speed_score = _reading_speed_penalty(words, constraints)

    boundary_bonus = 0.0
    if lead_gap is not None:
        boundary_bonus += 0.5 * _pause_score(lead_gap, constraints)
    if tail_gap is not None:
        boundary_bonus += 0.5 * _pause_score(tail_gap, constraints)

    if words:
        boundary_bonus += 0.6 * _punctuation_score(words[-1])
    if words:
        boundary_bonus -= 0.4 * _connector_penalty(words[0])
    if words and len(words) > 1:
        boundary_bonus -= 0.2 * _connector_penalty(words[-1])

    # Penalize creating additional chunks, especially very short ones.
    boundary_bonus -= constraints.break_penalty
    if len(words) <= 2:
        boundary_bonus -= 0.4
    if _chars(words) < max(6, int(constraints.preferred_chars * 0.35)):
        boundary_bonus -= 0.3

    return length_score + duration_score + speed_score + boundary_bonus


def _is_valid_chunk(words: Sequence[Dict[str, object]], constraints: _SubtitleConstraints) -> bool:
    if not words:
        return False
    chars = _chars(words)
    if chars == 0 or chars > constraints.max_chars:
        return False
    dur = _duration(words)
    if dur < constraints.min_duration or dur > constraints.max_duration:
        return False
    return True


def _finalize_chunk(words: Sequence[Dict[str, object]]) -> Dict[str, object]:
    chunk_words = list(words)
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


def _dynamic_split(
    words: Sequence[Dict[str, object]],
    constraints: _SubtitleConstraints,
) -> List[Sequence[Dict[str, object]]]:
    n = len(words)
    if n == 0:
        return []

    gaps = [0.0] * (n - 1)
    for i in range(n - 1):
        gaps[i] = _gap(words[i], words[i + 1])

    @lru_cache(maxsize=None)
    def best_cost(index: int) -> Tuple[float, Tuple[int, ...]]:
        if index >= n:
            return 0.0, ()

        best_value = float("-inf")
        best_path: Tuple[int, ...] = ()

        for j in range(index + 1, n + 1):
            chunk = words[index:j]
            lead_gap = None if index == 0 else gaps[index - 1]
            tail_gap = None if j == n else gaps[j - 1]

            if not _is_valid_chunk(chunk, constraints):
                continue

            chunk_cost = _chunk_score(chunk, constraints, lead_gap or 0.0, tail_gap or 0.0)
            remainder_cost, remainder_path = best_cost(j)
            total_cost = chunk_cost + remainder_cost

            if total_cost > best_value:
                best_value = total_cost
                best_path = (j,) + remainder_path

        return best_value, best_path

    best_value, best_indices = best_cost(0)

    if not best_indices or best_value == float("-inf"):
        return []

    segments: List[Sequence[Dict[str, object]]] = []
    prev = 0
    for idx in best_indices:
        segments.append(words[prev:idx])
        prev = idx
    return segments


def _fallback_split(
    words: Sequence[Dict[str, object]],
    constraints: _SubtitleConstraints,
) -> List[Sequence[Dict[str, object]]]:
    return [list(words)] if words else []


def _segment_words(
    segment: Dict[str, object],
    constraints: _SubtitleConstraints,
) -> List[Dict[str, object]]:
    words: List[Dict[str, object]] = [
        _normalize_word(word) for word in (segment.get("words") or []) if word is not None
    ]

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

    dynamic_chunks = _dynamic_split(words, constraints)
    if not dynamic_chunks:
        dynamic_chunks = _fallback_split(words, constraints)

    chunks = [_finalize_chunk(chunk) for chunk in dynamic_chunks]

    if chunks:
        chunks[0]["start"] = round(float(segment_start), 3)
        chunks[-1]["end"] = round(float(segment_end), 3)

    _segment_words._previous_end = float(segment_end)
    return chunks


def split_transcript_segments(
    transcript: Dict[str, object],
    config: PipelineConfig,
    context: PipelineContext,
) -> Tuple[Dict[str, object], Path]:
    """Split WhisperX output into shorter segments using rule-based optimization."""

    constraints = _SubtitleConstraints.from_config(config)
    segmented: List[Dict[str, object]] = []

    _segment_words._previous_end = 0.0
    for segment in transcript.get("segments", []):
        segmented.extend(_segment_words(segment, constraints))

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
