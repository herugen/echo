from __future__ import annotations

import json
from dataclasses import asdict
from pathlib import Path

from echo_engine.domain.models import Task


def write_manifest(task: Task) -> Path:
    path = task.asset_dir / "manifest.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = asdict(task)
    payload["input"]["kind"] = task.input.kind.value
    payload["config"]["output_dir"] = str(task.config.output_dir)
    payload["asset_dir"] = str(task.asset_dir)
    payload["status"] = task.status.value
    for stage in payload["stages"]:
        stage["status"] = stage["status"].value
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return path
