from __future__ import annotations

import argparse
import json
from pathlib import Path

from echo_engine.application.use_cases import retry_task
from echo_engine.infrastructure.task_repository import TaskRepository
from echo_engine.serialization import task_to_dict


def main() -> None:
    parser = argparse.ArgumentParser(description="Retry Echo task")
    parser.add_argument("task_id")
    parser.add_argument("--db-path", type=Path, required=True)
    args = parser.parse_args()
    repo = TaskRepository(args.db_path)

    def emit(task):
        print(json.dumps({"type": "task_updated", "task": task_to_dict(task)}, ensure_ascii=False), flush=True)

    task = retry_task(args.task_id, repo, emit)
    event_type = "task_failed" if task.status.value == "failed" else "task_completed"
    print(json.dumps({"type": event_type, "task": task_to_dict(task)}, ensure_ascii=False), flush=True)


if __name__ == "__main__":
    main()
