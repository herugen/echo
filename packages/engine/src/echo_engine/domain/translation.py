from __future__ import annotations

from dataclasses import asdict, dataclass, field


@dataclass(frozen=True)
class TranslationSegment:
    start: float
    end: float
    source_text: str
    translated_text: str


@dataclass(frozen=True)
class Translation:
    source_language: str
    target_language: str
    segments: list[TranslationSegment] = field(default_factory=list)

    def to_dict(self) -> dict:
        return asdict(self)
