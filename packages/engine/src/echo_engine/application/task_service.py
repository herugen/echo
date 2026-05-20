from __future__ import annotations

import json
import re
import shutil
from pathlib import Path
from uuid import uuid4
from collections.abc import Callable

from echo_engine.adapters.asr import JsonTranscriptStore, WhisperXAdapter
from echo_engine.adapters.downloaders import resolve_downloader
from echo_engine.adapters.media import extract_audio, probe_media
from echo_engine.adapters.subtitles import write_bilingual_srt, write_source_srt, write_translated_srt
from echo_engine.adapters.translation import DeepSeekTranslatorAdapter, JsonTranslationStore
from echo_engine.adapters.video_output import export_downloaded_video, export_sidecar_subtitles
from echo_engine.domain.models import (
    InputKind,
    StageRecord,
    StageStatus,
    Task,
    TaskConfig,
    TaskInput,
    TaskStatus,
)
from echo_engine.infrastructure.manifest_store import write_manifest
from echo_engine.infrastructure.task_repository import TaskRepository


def _slugify(value: str) -> str:
    stem = Path(value).stem or value
    slug = re.sub(r"[^a-zA-Z0-9\u4e00-\u9fff]+", "-", stem).strip("-").lower()
    return slug or "asset"


def _output_stem(task: Task, source_video: Path) -> str:
    if task.input.kind == InputKind.LOCAL_FILE:
        return Path(task.input.value).stem or source_video.stem or "asset"
    return source_video.stem or "asset"


def _asr_runtime_detail(runtime: dict) -> str:
    device = runtime.get("device") or "unknown"
    compute_type = runtime.get("compute_type") or "unknown"
    device_name = runtime.get("cuda_device_name")
    suffix = f" on {device_name}" if device == "cuda" and device_name else ""
    if runtime.get("fallback_reason"):
        return f"Audio transcribed with CPU/int8 after CUDA fallback: {runtime['fallback_reason']}"
    return f"Audio transcribed with {device}/{compute_type}{suffix}"


def _default_stages() -> list[StageRecord]:
    return [
        StageRecord("acquire_input"),
        StageRecord("probe_media"),
        StageRecord("extract_audio"),
        StageRecord("transcribe_audio"),
        StageRecord("generate_source_subtitles"),
        StageRecord("translate_segments"),
        StageRecord("generate_translated_subtitles"),
        StageRecord("generate_bilingual_subtitles"),
        StageRecord("finalize_video"),
    ]


def create_local_video_task(
    source_path: Path,
    output_root: Path,
    workspace_root: Path | None = None,
    target_language: str = "zh-CN",
    translator_backend: str = "deepseek",
    translator_base_url: str = "https://api.deepseek.com/v1",
    repository: TaskRepository | None = None,
) -> Task:
    source_path = source_path.expanduser().resolve()
    if not source_path.exists():
        raise FileNotFoundError(f"Video not found: {source_path}")

    task_id = str(uuid4())
    asset_root = (workspace_root or output_root).expanduser().resolve()
    asset_dir = asset_root / f"{_slugify(source_path.name)}-{task_id[:8]}"
    config = TaskConfig(
        output_dir=output_root.expanduser().resolve(),
        target_language=target_language,
        asr_backend="whisperx",
        translator_backend=translator_backend,
        translator_base_url=translator_base_url,
    )
    task = Task(
        id=task_id,
        title=source_path.name,
        input=TaskInput(kind=InputKind.LOCAL_FILE, value=str(source_path)),
        config=config,
        asset_dir=asset_dir,
        stages=_default_stages(),
    )
    write_manifest(task)
    if repository:
        repository.save(task)
    return task


def create_remote_video_task(
    url: str,
    output_root: Path,
    workspace_root: Path | None = None,
    target_language: str = "zh-CN",
    translator_backend: str = "deepseek",
    translator_base_url: str = "https://api.deepseek.com/v1",
    repository: TaskRepository | None = None,
) -> Task:
    if not url.strip():
        raise ValueError("URL is required")

    task_id = str(uuid4())
    asset_root = (workspace_root or output_root).expanduser().resolve()
    asset_dir = asset_root / f"remote-video-{task_id[:8]}"
    config = TaskConfig(
        output_dir=output_root.expanduser().resolve(),
        target_language=target_language,
        asr_backend="whisperx",
        translator_backend=translator_backend,
        translator_base_url=translator_base_url,
    )
    task = Task(
        id=task_id,
        title=url,
        input=TaskInput(kind=InputKind.REMOTE_URL, value=url),
        config=config,
        asset_dir=asset_dir,
        stages=_default_stages(),
    )
    write_manifest(task)
    if repository:
        repository.save(task)
    return task


def _load_transcript(path: Path):
    from echo_engine.domain.transcript import Transcript, TranscriptSegment

    payload = json.loads(path.read_text(encoding="utf-8"))
    return Transcript(
        language=payload.get("language", "unknown"),
        segments=[TranscriptSegment(**segment) for segment in payload.get("segments", [])],
    )


def _load_translation(path: Path):
    from echo_engine.domain.translation import Translation, TranslationSegment

    payload = json.loads(path.read_text(encoding="utf-8"))
    return Translation(
        source_language=payload.get("source_language", "unknown"),
        target_language=payload.get("target_language", "unknown"),
        segments=[TranslationSegment(**segment) for segment in payload.get("segments", [])],
    )


def _fail_task(
    task: Task,
    stage_index: int,
    error: Exception,
    repository: TaskRepository | None = None,
    on_update: Callable[[Task], None] | None = None,
) -> Task:
    task.status = TaskStatus.FAILED
    task.stages[stage_index].status = StageStatus.FAILED
    task.stages[stage_index].detail = str(error)
    task.metadata["error"] = {
        "stage": task.stages[stage_index].name,
        "message": str(error),
        "type": error.__class__.__name__,
    }
    write_manifest(task)
    if repository:
        repository.save(task)
    if on_update:
        on_update(task)
    return task


def _mark_stage_running(
    task: Task,
    stage_index: int,
    repository: TaskRepository | None = None,
    on_update: Callable[[Task], None] | None = None,
) -> None:
    task.current_stage = task.stages[stage_index].name
    task.stages[stage_index].status = StageStatus.RUNNING
    task.stages[stage_index].detail = "Running"
    write_manifest(task)
    if repository:
        repository.save(task)
    if on_update:
        on_update(task)


def run_video_task(
    task: Task,
    repository: TaskRepository | None = None,
    on_update: Callable[[Task], None] | None = None,
) -> Task:
    task.status = TaskStatus.RUNNING
    task.metadata["execution_config"] = {
        "asr_backend": task.config.asr_backend,
        "asr_model": task.config.asr_model,
        "translator_backend": task.config.translator_backend,
        "translator_model": DeepSeekTranslatorAdapter.default_model
        if task.config.translator_backend == "deepseek"
        else None,
        "translator_base_url": task.config.translator_base_url,
        "target_language": task.config.target_language,
        "downloader": task.config.downloader,
    }
    if on_update:
        on_update(task)

    source_dir = task.asset_dir / "source"
    subtitles_dir = task.asset_dir / "subtitles"
    transcripts_dir = task.asset_dir / "transcripts"
    video_dir = task.asset_dir / "video"
    for directory in (source_dir, subtitles_dir, transcripts_dir, video_dir):
        directory.mkdir(parents=True, exist_ok=True)

    _mark_stage_running(task, 0, repository, on_update)
    try:
        if task.stages[0].artifacts and Path(task.stages[0].artifacts[0]).exists():
            copied_source = Path(task.stages[0].artifacts[0])
            task.stages[0].status = StageStatus.SKIPPED
            task.stages[0].detail = "Existing source video reused"
        elif task.input.kind == InputKind.LOCAL_FILE:
            source_path = Path(task.input.value).expanduser().resolve()
            copied_source = source_dir / source_path.name
            if copied_source.exists():
                task.stages[0].status = StageStatus.SKIPPED
                task.stages[0].detail = "Existing local file reused"
            else:
                shutil.copy2(source_path, copied_source)
                task.stages[0].status = StageStatus.SUCCEEDED
                task.stages[0].detail = "Local file imported"
        elif task.input.kind == InputKind.REMOTE_URL:
            downloader = resolve_downloader(task.config.downloader)
            copied_source = downloader.download(task.input.value, source_dir)
            task.title = copied_source.name
            task.metadata["download"] = {"downloader": task.config.downloader, "source_url": task.input.value}
            task.stages[0].status = StageStatus.SUCCEEDED
            task.stages[0].detail = "Remote video downloaded"
        else:
            raise ValueError(f"Unsupported input kind: {task.input.kind}")
    except Exception as error:
        return _fail_task(task, 0, error, repository, on_update)
    task.stages[0].artifacts = [str(copied_source)]
    task.progress = 0.34
    write_manifest(task)
    if repository:
        repository.save(task)
    if on_update:
        on_update(task)

    _mark_stage_running(task, 1, repository, on_update)
    try:
        media_info = probe_media(copied_source)
    except Exception as error:
        return _fail_task(task, 1, error, repository, on_update)
    task.metadata["media"] = {
        "format_name": media_info.get("format", {}).get("format_name"),
        "duration": media_info.get("format", {}).get("duration"),
        "streams": [
            {
                "codec_type": stream.get("codec_type"),
                "codec_name": stream.get("codec_name"),
                "width": stream.get("width"),
                "height": stream.get("height"),
            }
            for stream in media_info.get("streams", [])
        ],
    }
    task.stages[1].status = StageStatus.SUCCEEDED
    task.stages[1].detail = "Media probed"
    task.progress = 0.67
    write_manifest(task)
    if repository:
        repository.save(task)
    if on_update:
        on_update(task)

    _mark_stage_running(task, 2, repository, on_update)
    extracted_audio = task.asset_dir / "audio" / "source.wav"
    try:
        if extracted_audio.exists():
            task.stages[2].status = StageStatus.SKIPPED
            task.stages[2].detail = "Existing extracted audio reused"
        else:
            extract_audio(copied_source, extracted_audio)
            task.stages[2].status = StageStatus.SUCCEEDED
            task.stages[2].detail = "Audio extracted"
    except Exception as error:
        return _fail_task(task, 2, error, repository, on_update)
    task.stages[2].artifacts = [str(extracted_audio)]
    task.progress = 0.84
    write_manifest(task)
    if repository:
        repository.save(task)
    if on_update:
        on_update(task)

    _mark_stage_running(task, 3, repository, on_update)
    transcript_path = task.asset_dir / "transcripts" / "transcript.json"
    try:
        if transcript_path.exists():
            task.metadata.setdefault(
                "asr_runtime",
                {
                    "backend": task.config.asr_backend,
                    "model": task.config.asr_model,
                    "device": "reused",
                },
            )
            task.stages[3].status = StageStatus.SKIPPED
            task.stages[3].detail = "Existing transcript reused"
        else:
            if task.config.asr_backend == "whisperx":
                adapter = WhisperXAdapter(
                    model_name=task.config.asr_model,
                )
                asr_runtime = adapter.runtime_info()
                task.metadata["asr_runtime"] = asr_runtime
                task.stages[3].detail = (
                    f"Preparing WhisperX model {task.config.asr_model} "
                    f"on {asr_runtime['device']}/{asr_runtime['compute_type']}"
                )
                if asr_runtime.get("cuda_device_name"):
                    task.stages[3].detail += f" ({asr_runtime['cuda_device_name']})"
                write_manifest(task)
                if repository:
                    repository.save(task)
                if on_update:
                    on_update(task)
            else:
                raise ValueError(f"Unsupported ASR backend: {task.config.asr_backend}")
            transcript = adapter.transcribe(extracted_audio)
            if task.config.asr_backend == "whisperx":
                task.metadata["asr_runtime"] = adapter.runtime_info()
            JsonTranscriptStore().write(transcript, transcript_path)
            task.metadata["transcript"] = {
                "language": transcript.language,
                "segment_count": len(transcript.segments),
            }
            task.stages[3].status = StageStatus.SUCCEEDED
            task.stages[3].detail = _asr_runtime_detail(task.metadata.get("asr_runtime", {}))
    except Exception as error:
        return _fail_task(task, 3, error, repository, on_update)
    task.stages[3].artifacts = [str(transcript_path)]
    task.progress = 0.88
    write_manifest(task)
    if repository:
        repository.save(task)
    if on_update:
        on_update(task)

    _mark_stage_running(task, 4, repository, on_update)
    source_srt_path = task.asset_dir / "subtitles" / "source.srt"
    try:
        if source_srt_path.exists():
            task.stages[4].status = StageStatus.SKIPPED
            task.stages[4].detail = "Existing source subtitles reused"
        else:
            write_source_srt(_load_transcript(transcript_path), source_srt_path)
            task.stages[4].status = StageStatus.SUCCEEDED
            task.stages[4].detail = "Source subtitles generated"
    except Exception as error:
        return _fail_task(task, 4, error, repository, on_update)
    task.stages[4].artifacts = [str(source_srt_path)]
    task.progress = 0.91
    write_manifest(task)
    if repository:
        repository.save(task)
    if on_update:
        on_update(task)

    _mark_stage_running(task, 5, repository, on_update)
    translation_path = task.asset_dir / "translations" / f"segments.{task.config.target_language}.json"
    try:
        if translation_path.exists():
            task.stages[5].status = StageStatus.SKIPPED
            task.stages[5].detail = "Existing translation reused"
        else:
            transcript = _load_transcript(transcript_path)
            if task.config.translator_backend == "deepseek":
                import os

                translator = DeepSeekTranslatorAdapter(
                    base_url=task.config.translator_base_url,
                    api_key=os.environ.get("DEEPSEEK_API_KEY", ""),
                )
            else:
                raise ValueError(f"Unsupported translator backend: {task.config.translator_backend}")
            translation = translator.translate(transcript, task.config.target_language)
            JsonTranslationStore().write(translation, translation_path)
            task.metadata["translation"] = {
                "target_language": translation.target_language,
                "model": translator.model if task.config.translator_backend == "deepseek" else None,
                "segment_count": len(translation.segments),
            }
            task.stages[5].status = StageStatus.SUCCEEDED
            task.stages[5].detail = "Segments translated"
    except Exception as error:
        return _fail_task(task, 5, error, repository, on_update)
    task.stages[5].artifacts = [str(translation_path)]
    task.progress = 0.94
    write_manifest(task)
    if repository:
        repository.save(task)
    if on_update:
        on_update(task)

    _mark_stage_running(task, 6, repository, on_update)
    translated_srt_path = task.asset_dir / "subtitles" / f"translated.{task.config.target_language}.srt"
    try:
        if translated_srt_path.exists():
            task.stages[6].status = StageStatus.SKIPPED
            task.stages[6].detail = "Existing translated subtitles reused"
        else:
            write_translated_srt(_load_translation(translation_path), translated_srt_path)
            task.stages[6].status = StageStatus.SUCCEEDED
            task.stages[6].detail = "Translated subtitles generated"
    except Exception as error:
        return _fail_task(task, 6, error, repository, on_update)
    task.stages[6].artifacts = [str(translated_srt_path)]
    task.progress = 0.97
    write_manifest(task)
    if repository:
        repository.save(task)
    if on_update:
        on_update(task)

    _mark_stage_running(task, 7, repository, on_update)
    bilingual_srt_path = task.asset_dir / "subtitles" / f"bilingual.{task.config.target_language}.srt"
    try:
        if bilingual_srt_path.exists():
            task.stages[7].status = StageStatus.SKIPPED
            task.stages[7].detail = "Existing bilingual subtitles reused"
        else:
            write_bilingual_srt(_load_translation(translation_path), bilingual_srt_path)
            task.stages[7].status = StageStatus.SUCCEEDED
            task.stages[7].detail = "Bilingual subtitles generated"
    except Exception as error:
        return _fail_task(task, 7, error, repository, on_update)
    task.stages[7].artifacts = [str(bilingual_srt_path)]
    task.progress = 0.985
    write_manifest(task)
    if repository:
        repository.save(task)
    if on_update:
        on_update(task)

    _mark_stage_running(task, 8, repository, on_update)
    export_dir = task.config.output_dir.expanduser().resolve()
    export_stem = _output_stem(task, copied_source)
    try:
        export_dir.mkdir(parents=True, exist_ok=True)
        exported_artifacts: list[Path] = []
        if task.input.kind == InputKind.REMOTE_URL:
            exported_video = export_downloaded_video(copied_source, export_dir)
            exported_artifacts.append(exported_video)
            export_stem = exported_video.stem or export_stem
        subtitle_copies = export_sidecar_subtitles(
            source_srt_path,
            translated_srt_path,
            bilingual_srt_path,
            export_dir,
            export_stem,
            task.config.target_language,
        )
        exported_artifacts.extend(subtitle_copies)
        task.stages[8].status = StageStatus.SUCCEEDED
        task.stages[8].detail = "Video asset and sidecar subtitles exported" if task.input.kind == InputKind.REMOTE_URL else "Sidecar subtitles exported"
    except Exception as error:
        return _fail_task(task, 8, error, repository, on_update)
    task.stages[8].artifacts = [str(path) for path in exported_artifacts]
    task.progress = 0.995
    write_manifest(task)
    if repository:
        repository.save(task)
    if on_update:
        on_update(task)

    task.progress = 1.0
    task.current_stage = None
    task.status = TaskStatus.SUCCEEDED
    write_manifest(task)
    if repository:
        repository.save(task)
    if on_update:
        on_update(task)
    return task


# Backward-compatible name for older development scripts.
prepare_local_video_task = run_video_task
