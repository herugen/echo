from __future__ import annotations

import shutil
from pathlib import Path


def export_downloaded_video(source_video: Path, output_dir: Path) -> Path:
    """Persist a remotely downloaded video as a user-facing media asset."""

    output_dir.mkdir(parents=True, exist_ok=True)
    output_path = output_dir / source_video.name
    if source_video.resolve() != output_path.resolve():
        shutil.copy2(source_video, output_path)
    return output_path


def export_sidecar_subtitles(
    source_srt: Path,
    translated_srt: Path,
    bilingual_srt: Path,
    output_dir: Path,
    output_stem: str,
    target_language: str,
) -> list[Path]:
    """Write long-lived sidecar subtitle files beside the user's media asset."""

    output_dir.mkdir(parents=True, exist_ok=True)
    copies = [
        (source_srt, output_dir / f"{output_stem}.source.srt"),
        (translated_srt, output_dir / f"{output_stem}.{target_language}.srt"),
        (bilingual_srt, output_dir / f"{output_stem}.bilingual.srt"),
    ]
    outputs: list[Path] = []
    for source, target in copies:
        if source.exists():
            shutil.copy2(source, target)
            outputs.append(target)
    return outputs
