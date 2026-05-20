from __future__ import annotations

import subprocess
import sys
from pathlib import Path
import shutil

from echo_engine.adapters.media import ensure_ffmpeg_cli_on_path, probe_media


VIDEO_EXTENSIONS = {".mp4", ".mkv", ".webm", ".mov"}


def _subprocess_no_window_kwargs() -> dict[str, int]:
    if sys.platform == "win32":
        return {"creationflags": subprocess.CREATE_NO_WINDOW}
    return {}


class DownloaderAdapter:
    def download(self, url: str, target_dir: Path) -> Path:
        raise NotImplementedError


class YtDlpDownloader(DownloaderAdapter):
    def __init__(self, executable: str = "yt-dlp") -> None:
        self.executable = executable

    def download(self, url: str, target_dir: Path) -> Path:
        target_dir.mkdir(parents=True, exist_ok=True)
        before = {path.resolve() for path in target_dir.glob("*") if path.is_file()}
        output_template = str(target_dir / "%(title).180B-%(id)s.%(ext)s")
        ensure_ffmpeg_cli_on_path()
        command = self._command(output_template, url)
        completed = subprocess.run(
            command,
            capture_output=True,
            text=True,
            check=False,
            **_subprocess_no_window_kwargs(),
        )
        if completed.returncode != 0:
            message = completed.stderr.strip() or completed.stdout.strip() or "yt-dlp failed"
            raise RuntimeError(message)

        candidates = [
            path
            for path in target_dir.glob("*")
            if path.is_file() and path.resolve() not in before and path.suffix.lower() in VIDEO_EXTENSIONS
        ]
        if not candidates:
            candidates = [
                path
                for path in target_dir.glob("*")
                if path.is_file() and path.suffix.lower() in VIDEO_EXTENSIONS
            ]
        video_candidates = [path for path in candidates if self._has_video_stream(path)]
        if not video_candidates:
            raise RuntimeError("yt-dlp completed but no downloaded video stream was found")
        return max(video_candidates, key=lambda path: path.stat().st_mtime)

    def _has_video_stream(self, path: Path) -> bool:
        media_info = probe_media(path)
        return any(stream.get("codec_type") == "video" for stream in media_info.get("streams", []))

    def _command(self, output_template: str, url: str) -> list[str]:
        args = [
            "--no-playlist",
            "--restrict-filenames",
            "-f",
            "bv*+ba/best",
            "--merge-output-format",
            "mp4",
            "-o",
            output_template,
            url,
        ]
        if shutil.which(self.executable):
            return [self.executable, *args]
        return [sys.executable, "-m", "yt_dlp", *args]


def resolve_downloader(name: str = "yt-dlp") -> DownloaderAdapter:
    if name not in {"yt-dlp", "ytdlp"}:
        raise ValueError("Echo MVP only supports yt-dlp for URL downloads")
    return YtDlpDownloader()
