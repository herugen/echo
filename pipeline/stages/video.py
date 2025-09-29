"""Video related stages."""

from __future__ import annotations

import json
import subprocess
from pathlib import Path

from ..config import PipelineConfig
from ..context import PipelineContext


def probe_video_format(
    source_video: Path,
    config: PipelineConfig,
    context: PipelineContext,
) -> Path:
    output = context.subpath("video", "format.json")
    cmd = [
        config.ffprobe_bin,
        "-v",
        "quiet",
        "-print_format",
        "json",
        "-show_streams",
        str(source_video),
    ]
    result = subprocess.run(cmd, capture_output=True, text=True, check=True)
    data = json.loads(result.stdout)

    info = {
        "width": None,
        "height": None,
    }
    for stream in data.get("streams", []):
        if stream.get("codec_type") == "video":
            info["width"] = stream.get("width")
            info["height"] = stream.get("height")
            break

    with output.open("w", encoding="utf-8") as fp:
        json.dump(info, fp, indent=2)

    return output

