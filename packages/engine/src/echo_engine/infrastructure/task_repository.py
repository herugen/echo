from __future__ import annotations

import json
import sqlite3
from dataclasses import asdict
from pathlib import Path

from echo_engine.domain.models import StageRecord, StageStatus, Task, TaskConfig, TaskInput, TaskStatus, InputKind


class TaskRepository:
    def __init__(self, db_path: Path) -> None:
        self.db_path = db_path
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._init_db()

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.db_path)
        connection.row_factory = sqlite3.Row
        return connection

    def _init_db(self) -> None:
        with self._connect() as connection:
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS tasks (
                    id TEXT PRIMARY KEY,
                    title TEXT NOT NULL,
                    status TEXT NOT NULL,
                    current_stage TEXT,
                    progress REAL NOT NULL,
                    input_kind TEXT NOT NULL,
                    input_value TEXT NOT NULL,
                    config_json TEXT NOT NULL,
                    asset_dir TEXT NOT NULL,
                    stages_json TEXT NOT NULL,
                    metadata_json TEXT NOT NULL,
                    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
                )
                """
            )

    def save(self, task: Task) -> None:
        config = asdict(task.config)
        config["output_dir"] = str(task.config.output_dir)
        stages = [
            {
                "name": stage.name,
                "status": stage.status.value,
                "detail": stage.detail,
                "artifacts": stage.artifacts,
            }
            for stage in task.stages
        ]
        with self._connect() as connection:
            connection.execute(
                """
                INSERT INTO tasks (
                    id, title, status, current_stage, progress, input_kind, input_value,
                    config_json, asset_dir, stages_json, metadata_json
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(id) DO UPDATE SET
                    title=excluded.title,
                    status=excluded.status,
                    current_stage=excluded.current_stage,
                    progress=excluded.progress,
                    input_kind=excluded.input_kind,
                    input_value=excluded.input_value,
                    config_json=excluded.config_json,
                    asset_dir=excluded.asset_dir,
                    stages_json=excluded.stages_json,
                    metadata_json=excluded.metadata_json,
                    updated_at=CURRENT_TIMESTAMP
                """,
                (
                    task.id,
                    task.title,
                    task.status.value,
                    task.current_stage,
                    task.progress,
                    task.input.kind.value,
                    task.input.value,
                    json.dumps(config, ensure_ascii=False),
                    str(task.asset_dir),
                    json.dumps(stages, ensure_ascii=False),
                    json.dumps(task.metadata, ensure_ascii=False),
                ),
            )


    def get(self, task_id: str) -> Task | None:
        with self._connect() as connection:
            row = connection.execute("SELECT * FROM tasks WHERE id = ?", (task_id,)).fetchone()
        return self._row_to_task(row) if row else None

    def delete(self, task_id: str) -> None:
        with self._connect() as connection:
            connection.execute("DELETE FROM tasks WHERE id = ?", (task_id,))

    def list_recent(self, limit: int = 50) -> list[Task]:
        with self._connect() as connection:
            rows = connection.execute(
                "SELECT * FROM tasks ORDER BY updated_at DESC LIMIT ?",
                (limit,),
            ).fetchall()
        tasks: list[Task] = []
        for row in rows:
            try:
                tasks.append(self._row_to_task(row))
            except Exception:
                # A desktop app should not fail to start because one historical
                # task was written by an older schema or interrupted build.
                continue
        return tasks

    def _row_to_task(self, row: sqlite3.Row) -> Task:
        config_payload = json.loads(row["config_json"])
        stages_payload = json.loads(row["stages_json"])
        return Task(
            id=row["id"],
            title=row["title"],
            input=TaskInput(kind=InputKind(row["input_kind"]), value=row["input_value"]),
            config=TaskConfig(
                **{
                    **config_payload,
                    "output_dir": Path(config_payload["output_dir"]),
                }
            ),
            asset_dir=Path(row["asset_dir"]),
            status=TaskStatus(row["status"]),
            current_stage=row["current_stage"],
            progress=row["progress"],
            stages=[
                StageRecord(
                    name=stage["name"],
                    status=StageStatus(stage["status"]),
                    detail=stage.get("detail"),
                    artifacts=stage.get("artifacts", []),
                )
                for stage in stages_payload
            ],
            metadata=json.loads(row["metadata_json"]),
        )
