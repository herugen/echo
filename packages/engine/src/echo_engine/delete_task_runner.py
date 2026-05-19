from __future__ import annotations

import argparse
from pathlib import Path

from echo_engine.application.use_cases import delete_task
from echo_engine.infrastructure.task_repository import TaskRepository


def main() -> None:
    parser = argparse.ArgumentParser(description="Delete Echo task")
    parser.add_argument("task_id")
    parser.add_argument("--db-path", type=Path, required=True)
    args = parser.parse_args()
    delete_task(args.task_id, TaskRepository(args.db_path))


if __name__ == "__main__":
    main()
