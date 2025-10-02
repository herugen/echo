"""Video download stage."""

from __future__ import annotations

import shlex
import shutil
from contextlib import suppress
from pathlib import Path, PurePosixPath
from typing import Any, Dict

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
    raw_dir.mkdir(parents=True, exist_ok=True)

    ydl_opts = {
        "outtmpl": str(raw_dir / "%(id)s.%(ext)s"),
        "quiet": True,
        "no_warnings": True,
        "noplaylist": True,
    }

    with YoutubeDL(ydl_opts) as ydl:
        info: Dict[str, Any] = ydl.extract_info(config.source_url, download=False)
        target = Path(ydl.prepare_filename(info))

    if target.exists():
        return target

    if config.remote_download_enabled:
        return _download_remote_via_ssh(config, context, info, target)

    with YoutubeDL(ydl_opts) as ydl:
        ydl.download([config.source_url])

    if not target.exists():
        raise RuntimeError("yt-dlp did not produce the expected video file")

    return target


def _download_remote_via_ssh(
    config: PipelineConfig, context: PipelineContext, info: Dict[str, Any], target: Path
) -> Path:
    try:
        import paramiko
    except ImportError as exc:  # pragma: no cover - defensive guard
        raise RuntimeError(
            "Remote download requires the 'paramiko' package. Please install it or disable remote downloads."
        ) from exc

    remote_base = str(config.remote_download_workdir).rstrip("/")
    remote_run_dir = PurePosixPath(remote_base) / context.slug / context.run_id
    remote_filename = info.get("_filename") or f"{info['id']}.{info['ext']}"
    # _filename may include templated directories; normalize to basename only
    remote_filename = remote_filename.split("/")[-1]
    remote_target = remote_run_dir / remote_filename
    remote_template = f"{remote_run_dir}/%(id)s.%(ext)s"

    client = paramiko.SSHClient()
    client.set_missing_host_key_policy(paramiko.AutoAddPolicy())

    try:
        client.connect(
            hostname=config.remote_download_host,
            username=config.remote_download_user,
            password=config.remote_download_password,
            look_for_keys=False,
            allow_agent=False,
        )

        remote_yt_dlp = shlex.quote(config.remote_download_yt_dlp_path or "yt-dlp")
        command = " && ".join(
            [
                f"mkdir -p {shlex.quote(str(remote_run_dir))}",
                f"if [ ! -f {shlex.quote(str(remote_target))} ]; then {remote_yt_dlp} --no-progress --no-warnings --no-playlist -o {shlex.quote(remote_template)} {shlex.quote(config.source_url)}; fi",
            ]
        )

        stdin, stdout, stderr = client.exec_command(command)
        exit_status = stdout.channel.recv_exit_status()
        if exit_status != 0:
            err_output = stderr.read().decode("utf-8", errors="ignore")
            out_output = stdout.read().decode("utf-8", errors="ignore")
            raise RuntimeError(
                "Remote yt-dlp execution failed"
                + (f"\nstdout: {out_output}" if out_output else "")
                + (f"\nstderr: {err_output}" if err_output else "")
            )

        sftp = client.open_sftp()
        try:
            sftp.get(str(remote_target), str(target))
        finally:
            sftp.close()
    finally:
        with suppress(Exception):  # pragma: no cover - cleanup
            client.close()

    if not target.exists():
        raise RuntimeError("Remote download did not produce the expected video file")

    return target

