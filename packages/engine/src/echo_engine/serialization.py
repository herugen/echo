from __future__ import annotations

from dataclasses import asdict

from echo_engine.domain.models import Task


def task_to_dict(task: Task) -> dict:
    payload = asdict(task)
    payload["input"]["kind"] = task.input.kind.value
    payload["config"]["output_dir"] = str(task.config.output_dir)
    payload["asset_dir"] = str(task.asset_dir)
    payload["status"] = task.status.value
    for stage in payload["stages"]:
        stage["status"] = stage["status"].value
    return payload
