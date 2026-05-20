from __future__ import annotations

import json
import os
import shutil
import subprocess
import tempfile
from pathlib import Path


def ensure_ffmpeg_cli_on_path() -> str:
    found = shutil.which("ffmpeg")
    if found:
        return found
    try:
        import imageio_ffmpeg

        bundled = Path(imageio_ffmpeg.get_ffmpeg_exe()).resolve()
    except Exception as error:
        raise FileNotFoundError("ffmpeg executable not found and bundled imageio-ffmpeg is unavailable") from error

    shim_dir = Path(tempfile.gettempdir()) / "echo-engine-bin"
    shim_dir.mkdir(parents=True, exist_ok=True)
    shim = shim_dir / ("ffmpeg.exe" if os.name == "nt" else "ffmpeg")
    if not shim.exists():
        try:
            shim.symlink_to(bundled)
        except OSError:
            shutil.copy2(bundled, shim)
        shim.chmod(shim.stat().st_mode | 0o111)

    path_entries = os.environ.get("PATH", "").split(os.pathsep) if os.environ.get("PATH") else []
    if str(shim_dir) not in path_entries:
        os.environ["PATH"] = str(shim_dir) + (os.pathsep + os.environ["PATH"] if os.environ.get("PATH") else "")
    return str(shim)


def _ffmpeg_executable() -> str:
    return ensure_ffmpeg_cli_on_path()


def _ffprobe_executable() -> str | None:
    return shutil.which("ffprobe")


def _subprocess_no_window_kwargs() -> dict[str, int]:
    if os.name == "nt":
        return {"creationflags": subprocess.CREATE_NO_WINDOW}
    return {}


def probe_media(source: Path) -> dict:
    ffprobe = _ffprobe_executable()
    if ffprobe:
        result = subprocess.run(
            [
                ffprobe,
                "-v",
                "quiet",
                "-print_format",
                "json",
                "-show_format",
                "-show_streams",
                str(source),
            ],
            check=True,
            capture_output=True,
            text=True,
            **_subprocess_no_window_kwargs(),
        )
        return json.loads(result.stdout)
    return _probe_media_with_av(source)


def _probe_media_with_av(source: Path) -> dict:
    import av

    with av.open(str(source)) as container:
        duration = None
        if container.duration is not None:
            duration = str(round(float(container.duration / av.time_base), 6))
        streams = []
        for stream in container.streams:
            streams.append(
                {
                    "codec_type": stream.type,
                    "codec_name": stream.codec_context.name if stream.codec_context else None,
                    "width": getattr(stream.codec_context, "width", None),
                    "height": getattr(stream.codec_context, "height", None),
                }
            )
        return {
            "format": {
                "format_name": source.suffix.lstrip(".") or "unknown",
                "duration": duration,
            },
            "streams": streams,
        }


def extract_audio(source: Path, target: Path) -> Path:
    target.parent.mkdir(parents=True, exist_ok=True)
    subprocess.run(
        [
            _ffmpeg_executable(),
            "-y",
            "-i",
            str(source),
            "-vn",
            "-ac",
            "1",
            "-ar",
            "16000",
            "-c:a",
            "pcm_s16le",
            str(target),
        ],
        check=True,
        capture_output=True,
        text=True,
        **_subprocess_no_window_kwargs(),
    )
    return target
