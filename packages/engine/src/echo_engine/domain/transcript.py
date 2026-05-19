from __future__ import annotations

from dataclasses import asdict, dataclass, field


@dataclass(frozen=True)
class TranscriptSegment:
    start: float
    end: float
    text: str


@dataclass(frozen=True)
class Transcript:
    language: str
    segments: list[TranscriptSegment] = field(default_factory=list)

    def to_dict(self) -> dict:
        return asdict(self)
