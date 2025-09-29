"""Context helpers for pipeline executions."""

from __future__ import annotations

import datetime as dt
import json
import hashlib
from pathlib import Path
from typing import Dict
from dataclasses import dataclass


def _slugify(text: str) -> str:
    slug = "".join(c if c.isalnum() else "-" for c in text).strip("-")
    slug = "-".join(filter(None, slug.split("-")))
    return slug or "job"


def _hash(text: str, length: int = 6) -> str:
    return hashlib.sha1(text.encode("utf-8")).hexdigest()[:length]


@dataclass
class PipelineContext:
    """Represents the filesystem context for a pipeline run."""

    root: Path
    slug: str
    run_id: str

    @classmethod
    def create(cls, workdir: Path, job_name: str, source_identifier: str) -> "PipelineContext":
        slug = _slugify(job_name or source_identifier)
        timestamp = dt.datetime.now().strftime("%Y%m%d-%H%M%S")
        run_hash = _hash(source_identifier + timestamp)
        run_id = f"{timestamp}-{run_hash}"
        root = workdir / slug / run_id
        return cls(root=root, slug=slug, run_id=run_id)

    @classmethod
    def from_existing(cls, workdir: Path, run_path: Path) -> "PipelineContext":
        slug = run_path.parent.name
        run_id = run_path.name
        return cls(root=run_path, slug=slug, run_id=run_id)

    def ensure_dirs(self) -> None:
        for sub in [
            "raw",
            "audio",
            "transcripts",
            "translations",
            "video",
            "logs",
            "tmp",
        ]:
            (self.root / sub).mkdir(parents=True, exist_ok=True)

    def subpath(self, *parts: str) -> Path:
        path = self.root.joinpath(*parts)
        path.parent.mkdir(parents=True, exist_ok=True)
        return path

    def write_metadata(self, data: Dict) -> None:
        metadata_path = self.root / "logs" / "metadata.json"
        metadata_path.parent.mkdir(parents=True, exist_ok=True)
        with metadata_path.open("w", encoding="utf-8") as fp:
            json.dump(data, fp, indent=2, ensure_ascii=False)

    def metadata_path(self) -> Path:
        return self.root / "logs" / "metadata.json"

