from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any


class TaskStatus(str, Enum):
    DRAFT = "draft"
    RUNNING = "running"
    FAILED = "failed"
    SUCCEEDED = "succeeded"
    CANCELLED = "cancelled"
    PAUSED = "paused"


class StageStatus(str, Enum):
    PENDING = "pending"
    RUNNING = "running"
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    SKIPPED = "skipped"


class InputKind(str, Enum):
    LOCAL_FILE = "local_file"
    REMOTE_URL = "remote_url"


@dataclass(frozen=True)
class TaskInput:
    kind: InputKind
    value: str


@dataclass(frozen=True)
class TaskConfig:
    output_dir: Path
    source_language: str | None = None
    target_language: str = "zh-CN"
    downloader: str = "yt-dlp"
    asr_model: str = "large-v3"
    asr_backend: str = "whisperx"
    translator_backend: str = "deepseek"
    translator_base_url: str = "https://api.deepseek.com/v1"
    generate_final_video: bool = False


@dataclass
class StageRecord:
    name: str
    status: StageStatus = StageStatus.PENDING
    detail: str | None = None
    artifacts: list[str] = field(default_factory=list)


@dataclass
class Task:
    id: str
    title: str
    input: TaskInput
    config: TaskConfig
    asset_dir: Path
    status: TaskStatus = TaskStatus.DRAFT
    current_stage: str | None = None
    progress: float = 0.0
    stages: list[StageRecord] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)
