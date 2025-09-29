"""Audio related stages."""

from __future__ import annotations

import subprocess
from pathlib import Path
from typing import Iterable, List

from ..config import PipelineConfig
from ..context import PipelineContext


def _run_ffmpeg(args: Iterable[str]) -> None:
    subprocess.run(list(args), check=True, capture_output=True, text=True)


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
    _run_ffmpeg(cmd)
    return target

