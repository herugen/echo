from __future__ import annotations

import argparse
import json
from pathlib import Path

from echo_engine.application.use_cases import create_local_import_task
from echo_engine.infrastructure.task_repository import TaskRepository
from echo_engine.serialization import task_to_dict


def main() -> None:
    parser = argparse.ArgumentParser(description="Create Echo local video task")
    parser.add_argument("source", type=Path)
    parser.add_argument("--output-root", type=Path, required=True)
    parser.add_argument("--workspace-root", type=Path)
    parser.add_argument("--target-language", default="zh-CN")
    parser.add_argument("--translator-base-url", default="https://api.deepseek.com/v1")
    parser.add_argument("--db-path", type=Path, required=True)
    args = parser.parse_args()
    repo = TaskRepository(args.db_path)
    task = create_local_import_task(
        args.source,
        args.output_root,
        args.workspace_root,
        args.target_language,
        "deepseek",
        args.translator_base_url,
        repo,
    )
    print(json.dumps(task_to_dict(task), ensure_ascii=False))


if __name__ == "__main__":
    main()
