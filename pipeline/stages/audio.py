"""Audio related stages."""

from __future__ import annotations

from pathlib import Path

from ..config import PipelineConfig
from ..context import PipelineContext
from ..utils import run_ffmpeg


def extract_audio_track(
    source_video: Path,
    config: PipelineConfig,
    context: PipelineContext,
) -> Path:
    target = context.subpath("audio", "source.wav")
    cmd = [
        config.ffmpeg_bin,
        "-y",
        "-i",
        str(source_video),
        "-vn",
        "-acodec",
        "pcm_s16le",
        "-ar",
        "44100",
        "-ac",
        "2",
        str(target),
    ]
    run_ffmpeg(cmd)
    return target

