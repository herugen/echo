"""Shared helpers for invoking ffmpeg consistently across stages."""

from __future__ import annotations

import platform
import subprocess
from typing import Iterable


def run_ffmpeg(args: Iterable[str]) -> None:
    """Execute an ffmpeg command, enabling hardware accel on macOS."""

    cmd = list(args)
    if platform.system() == "Darwin" and "-hwaccel" not in cmd:
        cmd = [cmd[0], "-hwaccel", "videotoolbox", *cmd[1:]]

    subprocess.run(cmd, check=True, capture_output=True, text=True)

