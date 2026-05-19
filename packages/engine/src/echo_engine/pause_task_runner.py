from __future__ import annotations

import argparse
import json
from pathlib import Path

from echo_engine.application.use_cases import pause_task
from echo_engine.infrastructure.task_repository import TaskRepository
from echo_engine.serialization import task_to_dict


def main() -> None:
    parser = argparse.ArgumentParser(description="Pause Echo task")
    parser.add_argument("task_id")
    parser.add_argument("--db-path", type=Path, required=True)
    args = parser.parse_args()
    task = pause_task(args.task_id, TaskRepository(args.db_path))
    print(json.dumps(task_to_dict(task), ensure_ascii=False), flush=True)


if __name__ == "__main__":
    main()
