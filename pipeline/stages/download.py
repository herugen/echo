"""Video download stage."""

from __future__ import annotations

import shutil
from pathlib import Path

from yt_dlp import YoutubeDL

from ..config import PipelineConfig
from ..context import PipelineContext


def download_video(config: PipelineConfig, context: PipelineContext) -> Path:
    if config.local_video:
        source = Path(config.local_video)
        target = context.subpath("raw", source.name)
        if not target.exists():
            shutil.copyfile(source, target)
        return target

    if not config.source_url:
        raise ValueError("source_url is required for downloading")

    raw_dir = context.root / "raw"
    ydl_opts = {
        "outtmpl": str(raw_dir / "%(id)s.%(ext)s"),
        "quiet": True,
        "no_warnings": True,
        "noplaylist": True,
    }

    with YoutubeDL(ydl_opts) as ydl:
        info = ydl.extract_info(config.source_url, download=False)
        target = Path(ydl.prepare_filename(info))

        if target.exists():
            return target

        ydl.download([config.source_url])

    if not target.exists():
        raise RuntimeError("yt-dlp did not produce the expected video file")

    return target

