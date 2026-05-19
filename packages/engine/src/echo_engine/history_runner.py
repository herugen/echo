from __future__ import annotations

import argparse
import json
from dataclasses import asdict
from pathlib import Path

from echo_engine.infrastructure.task_repository import TaskRepository


def main() -> None:
    parser = argparse.ArgumentParser(description="Echo engine task history entrypoint")
    parser.add_argument("--db-path", type=Path, required=True)
    args = parser.parse_args()

    tasks = TaskRepository(args.db_path).list_recent()
    payload = []
    for task in tasks:
        item = asdict(task)
        item["input"]["kind"] = task.input.kind.value
        item["config"]["output_dir"] = str(task.config.output_dir)
        item["asset_dir"] = str(task.asset_dir)
        item["status"] = task.status.value
        for stage in item["stages"]:
            stage["status"] = stage["status"].value
        payload.append(item)
    print(json.dumps(payload, ensure_ascii=False))


if __name__ == "__main__":
    main()
