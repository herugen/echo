from __future__ import annotations

from pathlib import Path

from echo_engine.application.task_service import create_local_video_task, create_remote_video_task, run_video_task
from echo_engine.domain.models import Task
from echo_engine.infrastructure.task_repository import TaskRepository


def import_local_video(
    source_path: Path,
    output_root: Path,
    workspace_root: Path | None = None,
    target_language: str = "zh-CN",
    translator_backend: str = "deepseek",
    translator_base_url: str = "https://api.deepseek.com/v1",
    repository: TaskRepository | None = None,
) -> Task:
    task = create_local_import_task(
        source_path, output_root, workspace_root, target_language, translator_backend, translator_base_url, repository
    )
    return run_video_task(task, repository)


def create_local_import_task(
    source_path: Path,
    output_root: Path,
    workspace_root: Path | None = None,
    target_language: str = "zh-CN",
    translator_backend: str = "deepseek",
    translator_base_url: str = "https://api.deepseek.com/v1",
    repository: TaskRepository | None = None,
) -> Task:
    return create_local_video_task(
        source_path=source_path,
        output_root=output_root,
        workspace_root=workspace_root,
        target_language=target_language,
        translator_backend=translator_backend,
        translator_base_url=translator_base_url,
        repository=repository,
    )


def create_url_import_task(
    url: str,
    output_root: Path,
    workspace_root: Path | None = None,
    target_language: str = "zh-CN",
    translator_backend: str = "deepseek",
    translator_base_url: str = "https://api.deepseek.com/v1",
    repository: TaskRepository | None = None,
) -> Task:
    return create_remote_video_task(
        url=url,
        output_root=output_root,
        workspace_root=workspace_root,
        target_language=target_language,
        translator_backend=translator_backend,
        translator_base_url=translator_base_url,
        repository=repository,
    )


def run_task(task_id: str, repository: TaskRepository, on_update=None) -> Task:
    task = repository.get(task_id)
    if task is None:
        raise ValueError(f"Task not found: {task_id}")
    return run_video_task(task, repository, on_update)


def retry_task(task_id: str, repository: TaskRepository, on_update=None) -> Task:
    task = repository.get(task_id)
    if task is None:
        raise ValueError(f"Task not found: {task_id}")
    task.status = task.status.DRAFT
    task.metadata.pop("error", None)
    for stage in task.stages:
        if stage.status.value == "failed":
            stage.status = stage.status.PENDING
            stage.detail = None
    repository.save(task)
    return run_video_task(task, repository, on_update)


def pause_task(task_id: str, repository: TaskRepository) -> Task:
    task = repository.get(task_id)
    if task is None:
        raise ValueError(f"Task not found: {task_id}")
    task.status = task.status.PAUSED
    task.metadata["paused"] = True
    repository.save(task)
    return task


def delete_task(task_id: str, repository: TaskRepository, delete_workspace: bool = True) -> None:
    task = repository.get(task_id)
    if task is None:
        return
    if task.status.value == "running":
        raise ValueError("Running tasks must be paused before deletion")
    repository.delete(task_id)
    if delete_workspace and task.asset_dir.exists():
        import shutil

        shutil.rmtree(task.asset_dir, ignore_errors=True)
