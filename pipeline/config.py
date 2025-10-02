"""Pipeline configuration models and helpers."""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional, Set

from dotenv import load_dotenv

load_dotenv()


@dataclass
class PipelineConfig:
    """Holds runtime configuration for a translation run."""

    target_language: str = "zh"
    source_url: Optional[str] = None
    local_video: Optional[Path] = None
    job_name: Optional[str] = None
    reuse_run: Optional[str] = None
    workdir: Path = Path("runs")
    keep_temp: bool = False
    force_steps: Set[str] = field(default_factory=set)
    whisper_model: str = "large-v3"
    whisper_device: str = "cpu"
    whisper_compute_type: str = "int8"
    whisper_batch_size: int = 16
    whisper_vad_method: str = "silero"
    whisper_vad_onset: float = 0.5
    whisper_vad_offset: float = 0.363
    whisper_vad_chunk_size: int = 15
    whisper_segment_max_words: int = 20
    whisper_segment_max_chars: int = 80
    whisper_cache_dir: Path = Path.home() / ".cache"
    whisper_docker_image: str = "whisperx-runner:latest"
    whisper_docker_args: Optional[str] = None
    deepseek_base_url: str = "https://api.deepseek.com/v1"
    deepseek_api_key: Optional[str] = None
    tts_service_url: Optional[str] = None
    ffmpeg_bin: str = "ffmpeg"
    ffprobe_bin: str = "ffprobe"
    remote_download_host: Optional[str] = None
    remote_download_user: Optional[str] = None
    remote_download_password: Optional[str] = None
    remote_download_workdir: str = "/tmp/echo-downloads"
    remote_download_yt_dlp_path: str = "yt-dlp"

    def validate(self) -> None:
        if not self.source_url and not self.local_video:
            raise ValueError("Either source_url or local_video must be provided.")
        if self.local_video and not self.local_video.exists():
            raise FileNotFoundError(f"Local video not found: {self.local_video}")
        remote_fields = [
            self.remote_download_host,
            self.remote_download_user,
            self.remote_download_password,
        ]
        if any(remote_fields) and not self.remote_download_enabled:
            raise ValueError(
                "Remote download requires remote_download_host, remote_download_user, and remote_download_password."
            )

    @property
    def remote_download_enabled(self) -> bool:
        return bool(self.remote_download_host and self.remote_download_user and self.remote_download_password)

def _env_bool(name: str) -> Optional[bool]:
    value = os.getenv(name)
    if value is None:
        return None
    return value.strip().lower() in {"1", "true", "yes", "on"}


def _env_path(name: str) -> Optional[Path]:
    value = os.getenv(name)
    if not value:
        return None
    return Path(value).expanduser()


def _env_int(name: str) -> Optional[int]:
    value = os.getenv(name)
    if value is None:
        return None
    try:
        return int(value)
    except ValueError:
        raise ValueError(f"Environment variable {name} must be an integer") from None


def _env_float(name: str) -> Optional[float]:
    value = os.getenv(name)
    if value is None:
        return None
    try:
        return float(value)
    except ValueError:
        raise ValueError(f"Environment variable {name} must be a float") from None


def _env_set(name: str) -> Optional[Set[str]]:
    value = os.getenv(name)
    if not value:
        return None
    items = {item.strip() for item in value.split(",") if item.strip()}
    return items or None


def load_config(**kwargs) -> PipelineConfig:
    """Creates a PipelineConfig object by layering defaults, env vars, and overrides."""

    config = PipelineConfig()

    env_overrides = {
        "source_url": os.getenv("SOURCE_URL"),
        "local_video": _env_path("LOCAL_VIDEO"),
        "target_language": os.getenv("TARGET_LANGUAGE"),
        "job_name": os.getenv("JOB_NAME"),
        "reuse_run": os.getenv("REUSE_RUN"),
        "workdir": _env_path("WORKDIR"),
        "whisper_model": os.getenv("WHISPER_MODEL"),
        "whisper_device": os.getenv("WHISPER_DEVICE"),
        "whisper_compute_type": os.getenv("WHISPER_COMPUTE_TYPE"),
        "whisper_vad_method": os.getenv("WHISPER_VAD_METHOD"),
        "whisper_segment_max_words": _env_int("WHISPER_SEGMENT_MAX_WORDS"),
        "whisper_segment_max_chars": _env_int("WHISPER_SEGMENT_MAX_CHARS"),
        "whisper_cache_dir": _env_path("WHISPER_CACHE_DIR"),
        "whisper_docker_image": os.getenv("WHISPER_DOCKER_IMAGE"),
        "whisper_docker_args": os.getenv("WHISPER_DOCKER_ARGS"),
        "deepseek_base_url": os.getenv("DEEPSEEK_BASE_URL"),
        "deepseek_api_key": os.getenv("DEEPSEEK_API_KEY"),
        "tts_service_url": os.getenv("TTS_SERVICE_URL"),
        "ffmpeg_bin": os.getenv("FFMPEG_BIN"),
        "ffprobe_bin": os.getenv("FFPROBE_BIN"),
        "remote_download_host": os.getenv("REMOTE_DOWNLOAD_HOST"),
        "remote_download_user": os.getenv("REMOTE_DOWNLOAD_USER"),
        "remote_download_password": os.getenv("REMOTE_DOWNLOAD_PASSWORD"),
        "remote_download_workdir": os.getenv("REMOTE_DOWNLOAD_WORKDIR"),
        "remote_download_yt_dlp_path": os.getenv("REMOTE_DOWNLOAD_YT_DLP_PATH"),
    }

    keep_temp_env = _env_bool("KEEP_TEMP")
    if keep_temp_env is not None:
        config.keep_temp = keep_temp_env

    force_env = _env_set("FORCE_STEPS")
    if force_env:
        config.force_steps = force_env

    batch_env = _env_int("WHISPER_BATCH_SIZE")
    if batch_env is not None:
        config.whisper_batch_size = batch_env

    vad_onset_env = _env_float("WHISPER_VAD_ONSET")
    if vad_onset_env is not None:
        config.whisper_vad_onset = vad_onset_env

    vad_offset_env = _env_float("WHISPER_VAD_OFFSET")
    if vad_offset_env is not None:
        config.whisper_vad_offset = vad_offset_env

    vad_chunk_env = _env_int("WHISPER_VAD_CHUNK_SIZE")
    if vad_chunk_env is not None:
        config.whisper_vad_chunk_size = vad_chunk_env

    for key, value in env_overrides.items():
        if value is not None:
            setattr(config, key, value)

    force_override = kwargs.pop("force_steps", None)
    for key, value in kwargs.items():
        if value is None:
            continue
        if key in {"local_video", "workdir"} and isinstance(value, Path):
            value = value.expanduser()
        setattr(config, key, value)

    if force_override:
        config.force_steps = set(force_override)

    if "keep_temp" in kwargs and kwargs["keep_temp"] is not None:
        config.keep_temp = bool(kwargs["keep_temp"])

    config.validate()
    return config

