"""Video subtitle burning stage."""

from __future__ import annotations

from pathlib import Path

from ..config import PipelineConfig
from ..context import PipelineContext
from ..utils import run_ffmpeg


def burn_translated_subtitles(
    source_video: Path,
    translated_subtitles: Path,
    config: PipelineConfig,
    context: PipelineContext,
) -> Path:
    """Render translated subtitles directly into the video frames."""

    output_path = context.subpath("video", "with-translated-subs.mp4")

    subtitle_path = translated_subtitles.resolve()
    subtitle_arg = _escape_subtitle_path(subtitle_path)
    force_style = "BackColour=&HA0000000,BorderStyle=4,Fontsize=18"
    filter_expr = f"subtitles='{subtitle_arg}':force_style='{force_style}'"

    cmd = [
        config.ffmpeg_bin,
        "-y",
        "-i",
        str(source_video),
        "-vf",
        filter_expr,
        "-c:v",
        config.overlay_video_codec,
        "-pix_fmt",
        "yuv420p",
    ]

    if not config.overlay_video_bitrate and config.overlay_video_crf is not None:
        cmd.extend(["-crf", str(config.overlay_video_crf)])

    if config.overlay_video_bitrate:
        cmd.extend(["-b:v", config.overlay_video_bitrate])

    if config.overlay_video_preset:
        cmd.extend(["-preset", config.overlay_video_preset])

    cmd.extend([
        "-c:a",
        "copy",
        str(output_path),
    ])

    run_ffmpeg(cmd)
    return output_path


def _escape_subtitle_path(path: Path) -> str:
    text = path.as_posix()
    text = text.replace("\\", "\\\\")
    text = text.replace(":", "\\:")
    text = text.replace("'", "\\'")
    text = text.replace(",", "\\,")
    return text

