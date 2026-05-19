from __future__ import annotations

import argparse
import json
from dataclasses import asdict
from pathlib import Path

from echo_engine.application.use_cases import import_local_video
from echo_engine.infrastructure.task_repository import TaskRepository


def main() -> None:
    parser = argparse.ArgumentParser(description="Echo engine local developer entrypoint")
    parser.add_argument("source", type=Path)
    parser.add_argument("--output-root", type=Path, required=True)
    parser.add_argument("--target-language", default="zh-CN")
    parser.add_argument("--translator-base-url", default="https://api.deepseek.com/v1")
    parser.add_argument("--db-path", type=Path)
    args = parser.parse_args()

    repository = TaskRepository(args.db_path) if args.db_path else None
    task = import_local_video(
        args.source,
        args.output_root,
        None,
        args.target_language,
        "deepseek",
        args.translator_base_url,
        repository,
    )
    payload = asdict(task)
    payload["input"]["kind"] = task.input.kind.value
    payload["config"]["output_dir"] = str(task.config.output_dir)
    payload["asset_dir"] = str(task.asset_dir)
    payload["status"] = task.status.value
    for stage in payload["stages"]:
        stage["status"] = stage["status"].value
    print(json.dumps(payload, ensure_ascii=False))


if __name__ == "__main__":
    main()
