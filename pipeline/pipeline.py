"""Main pipeline orchestrator."""

from __future__ import annotations

import json
from pathlib import Path
from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Tuple

from .config import PipelineConfig
from .context import PipelineContext
from .stages import (
    download_video,
    probe_video_format,
    extract_audio_track,
    transcribe_audio,
    normalize_transcript,
    split_transcript_segments,
    translate_segments,
    generate_source_subtitles,
    generate_translated_subtitles,
    burn_translated_subtitles,
)


_STAGE_SEQUENCE = [
    "download",
    "probe_video",
    "extract_audio",
    "transcribe",
    "normalize",
    "segment",
    "subtitle_source",
    "translate",
    "subtitle_translated",
    "burn_translated_subtitles",
]

_STAGE_INDEX = {name: index for index, name in enumerate(_STAGE_SEQUENCE)}

_STAGE_ARTIFACT_KEYS = {
    "download": ("video",),
    "probe_video": ("video_format",),
    "extract_audio": ("audio",),
    "transcribe": ("transcript_raw",),
    "normalize": ("transcript_normalized",),
    "segment": ("transcript",),
    "translate": ("translated_segments",),
    "subtitle_source": ("subtitle_source",),
    "subtitle_translated": ("subtitle_translated",),
    "burn_translated_subtitles": ("video_final",),
}


def _normalize_stage_name(raw: str) -> str:
    candidate = raw.strip().lower().replace("-", "_")
    if candidate not in _STAGE_INDEX:
        available = ", ".join(_STAGE_SEQUENCE)
        raise ValueError(f"Unknown stage '{raw}'. Available stages: {available}")
    return candidate


def _locate_existing_run(workdir: Path, reuse_run: str) -> Path:
    run_hint = Path(reuse_run)
    if run_hint.is_absolute():
        run_path = run_hint
    else:
        run_path = workdir / run_hint
        if not run_path.exists():
            for slug_dir in workdir.iterdir():
                candidate = slug_dir / reuse_run
                if candidate.exists():
                    run_path = candidate
                    break
    if not run_path.exists():
        raise FileNotFoundError(f"Cannot locate run directory for '{reuse_run}'")
    if not run_path.is_dir():
        raise NotADirectoryError(f"Run path '{run_path}' is not a directory")
    return run_path


def _load_existing_metadata(context: PipelineContext) -> Tuple[Dict[str, Any], Path]:
    metadata_path = context.metadata_path()
    if not metadata_path.exists():
        raise FileNotFoundError(
            f"Cannot resume pipeline: metadata file not found at {metadata_path}"
        )
    with metadata_path.open("r", encoding="utf-8") as fp:
        data = json.load(fp)
    if not isinstance(data, dict):
        raise ValueError("Metadata file is malformed; expected a JSON object")
    return data, metadata_path


def _artifact_path(context: PipelineContext, artifacts: Dict[str, Any], key: str, stage: str) -> Path:
    value = artifacts.get(key)
    if not value:
        raise KeyError(f"Artifact '{key}' required for stage '{stage}' is missing")
    raw_path = Path(value)
    candidates = [raw_path]

    if not raw_path.is_absolute():
        try:
            relative = raw_path.relative_to(context.root)
            candidates.append(context.root / relative)
        except ValueError:
            candidates.append(context.root / raw_path)

    for candidate in candidates:
        if candidate.exists():
            return candidate

    raise FileNotFoundError(
        f"Artifact '{key}' for stage '{stage}' not found. Checked: {', '.join(str(c) for c in candidates)}"
    )


def _load_json_file(path: Path, stage: str) -> Any:
    if not path.exists():
        raise FileNotFoundError(f"Stage '{stage}' expected JSON at {path} but file is absent")
    with path.open("r", encoding="utf-8") as fp:
        return json.load(fp)


def _build_resume_plan(
    context: PipelineContext,
    config: PipelineConfig,
    metadata: Dict[str, Any],
) -> Tuple[List[Dict[str, Any]], int, Dict[str, Any]]:
    artifacts = metadata.get("artifacts") or {}
    completed_stages = metadata.get("stages") or []
    stage_meta_map = {stage.get("name"): stage for stage in completed_stages if stage.get("name")}
    completed_names = [name for name in _STAGE_SEQUENCE if name in stage_meta_map]

    force_steps: set[str] = set()
    for step in config.force_steps or set():
        normalized = _normalize_stage_name(step)
        force_steps.add(normalized)

    if config.resume_from_stage:
        resume_stage = _normalize_stage_name(config.resume_from_stage)
        resume_index = _STAGE_INDEX[resume_stage]
    else:
        resume_index = len(completed_names)

    if force_steps:
        resume_index = min(resume_index, min(_STAGE_INDEX[name] for name in force_steps))

    plan: List[Dict[str, Any]] = []
    prepared: Dict[str, Any] = {}

    for index, stage_name in enumerate(_STAGE_SEQUENCE):
        is_forced = stage_name in force_steps

        if not is_forced:
            for artifact_key in _STAGE_ARTIFACT_KEYS.get(stage_name, tuple()):
                if artifact_key not in artifacts:
                    continue
                path = _artifact_path(context, artifacts, artifact_key, stage_name)
                if stage_name == "download":
                    prepared.setdefault("video_path", path)
                elif stage_name == "probe_video":
                    prepared.setdefault("format_path", path)
                elif stage_name == "extract_audio":
                    prepared.setdefault("audio_path", path)
                elif stage_name == "transcribe":
                    prepared.setdefault("transcript_path", path)
                    prepared.setdefault("transcript", _load_json_file(path, stage_name))
                elif stage_name == "normalize":
                    prepared.setdefault("normalized_path", path)
                    prepared.setdefault("normalized", _load_json_file(path, stage_name))
                elif stage_name == "segment":
                    prepared.setdefault("segments_path", path)
                    prepared.setdefault("segments", _load_json_file(path, stage_name))
                elif stage_name == "translate":
                    prepared.setdefault("translated_path", path)
                    prepared.setdefault("translated", _load_json_file(path, stage_name))
                elif stage_name == "subtitle_source":
                    prepared.setdefault("source_subtitle_path", path)
                elif stage_name == "subtitle_translated":
                    prepared.setdefault("translated_subtitle_path", path)
                elif stage_name == "burn_translated_subtitles":
                    prepared.setdefault("final_video_path", path)

        if index < resume_index:
            if stage_name not in stage_meta_map:
                raise ValueError(
                    f"Cannot resume pipeline: stage '{stage_name}' has not completed yet"
                )
            plan.append({"name": stage_name, "skip": True, "meta": stage_meta_map[stage_name]})
            continue

        plan.append({"name": stage_name, "skip": False, "forced": is_forced})

    return plan, resume_index, prepared


@dataclass
class PipelineResult:
    run_id: str
    output_video: Optional[str]
    context: PipelineContext
    artifacts: Dict[str, str]


def run_pipeline(config: PipelineConfig) -> PipelineResult:
    """Run the translation pipeline synchronously based on configuration."""

    if config.reuse_run:
        run_path = _locate_existing_run(config.workdir, config.reuse_run)
        context = PipelineContext.from_existing(config.workdir, run_path)
    else:
        context = PipelineContext.create(
            workdir=config.workdir,
            job_name=config.job_name or "video-translation",
            source_identifier=config.source_url or str(config.local_video),
        )
    context.ensure_dirs()

    if config.reuse_run:
        existing_metadata, _ = _load_existing_metadata(context)
    else:
        existing_metadata = None

    metadata: Dict[str, Any] = existing_metadata.copy() if existing_metadata else {}
    metadata.setdefault("config", {})
    metadata.setdefault("artifacts", {})
    metadata.setdefault("stages", [])

    metadata["config"].update(
        {
            "target_language": config.target_language,
            "source_url": config.source_url,
            "local_video": str(config.local_video) if config.local_video else None,
            "whisper_model": config.whisper_model,
        }
    )

    plan, _resume_index, prepared = _build_resume_plan(context, config, metadata)

    artifacts = metadata.setdefault("artifacts", {})

    def _ensure_path(value: Any) -> Optional[Path]:
        if value is None:
            return None
        return value if isinstance(value, Path) else Path(value)

    video_path = _ensure_path(prepared.get("video_path") or artifacts.get("video"))
    format_path = _ensure_path(prepared.get("format_path") or artifacts.get("video_format"))
    audio_path = _ensure_path(prepared.get("audio_path") or artifacts.get("audio"))
    transcript_path = _ensure_path(prepared.get("transcript_path") or artifacts.get("transcript_raw"))
    transcript = prepared.get("transcript")
    normalized_path = _ensure_path(prepared.get("normalized_path") or artifacts.get("transcript_normalized"))
    normalized_transcript = prepared.get("normalized")
    segmented_path = _ensure_path(prepared.get("segments_path") or artifacts.get("transcript"))
    segmented_transcript = prepared.get("segments")
    translated_path = _ensure_path(prepared.get("translated_path") or artifacts.get("translated_segments"))
    translated_segments = prepared.get("translated")
    source_subtitle = _ensure_path(prepared.get("source_subtitle_path") or artifacts.get("subtitle_source"))
    translated_subtitle = _ensure_path(prepared.get("translated_subtitle_path") or artifacts.get("subtitle_translated"))
    final_video = _ensure_path(prepared.get("final_video_path") or artifacts.get("video_final"))

    stages: List[Dict[str, Any]] = []

    for state in plan:
        stage_name = state["name"]
        skip_stage = state["skip"]
        forced_stage = state.get("forced", False)

        if skip_stage:
            meta_entry = state.get("meta") or {"name": stage_name}
            stages.append(meta_entry)

            if stage_name == "download" and video_path is None:
                raise RuntimeError("Cannot resume pipeline: missing video artifact for skipped 'download' stage.")
            if stage_name == "probe_video" and format_path is None:
                raise RuntimeError("Cannot resume pipeline: missing format artifact for skipped 'probe_video' stage.")
            if stage_name == "extract_audio" and audio_path is None:
                raise RuntimeError("Cannot resume pipeline: missing audio artifact for skipped 'extract_audio' stage.")
            if stage_name == "transcribe" and (transcript is None or transcript_path is None):
                raise RuntimeError("Cannot resume pipeline: missing transcript artifact for skipped 'transcribe' stage.")
            if stage_name == "normalize" and (normalized_transcript is None or normalized_path is None):
                raise RuntimeError("Cannot resume pipeline: missing normalized transcript for skipped 'normalize' stage.")
            if stage_name == "segment" and (segmented_transcript is None or segmented_path is None):
                raise RuntimeError("Cannot resume pipeline: missing segmented transcript for skipped 'segment' stage.")
            if stage_name == "translate" and (translated_segments is None or translated_path is None):
                raise RuntimeError("Cannot resume pipeline: missing translated segments for skipped 'translate' stage.")
            if stage_name == "subtitle_source" and source_subtitle is None:
                raise RuntimeError("Cannot resume pipeline: missing source subtitle file for skipped 'subtitle_source' stage.")
            if stage_name == "subtitle_translated" and translated_subtitle is None:
                raise RuntimeError("Cannot resume pipeline: missing translated subtitle file for skipped 'subtitle_translated' stage.")
            if stage_name == "burn_translated_subtitles" and final_video is None:
                raise RuntimeError("Cannot resume pipeline: missing final video for skipped 'burn_translated_subtitles' stage.")

            continue

        if stage_name == "download":
            if forced_stage or video_path is None:
                video_path = download_video(config, context)
            artifacts["video"] = str(video_path)
            stages.append({"name": "download", "path": str(video_path)})

        elif stage_name == "probe_video":
            if video_path is None:
                raise RuntimeError("Probe stage requires a downloaded video artifact.")
            if forced_stage or format_path is None:
                format_path = probe_video_format(video_path, config, context)
            artifacts["video_format"] = str(format_path)
            stages.append({"name": "probe_video", "path": str(format_path)})

        elif stage_name == "extract_audio":
            if video_path is None:
                raise RuntimeError("Audio extraction requires a downloaded video artifact.")
            if forced_stage or audio_path is None:
                audio_path = extract_audio_track(video_path, config, context)
            artifacts["audio"] = str(audio_path)
            stages.append({"name": "extract_audio", "path": str(audio_path)})

        elif stage_name == "transcribe":
            if audio_path is None:
                raise RuntimeError("Transcription requires an extracted audio track.")
            if forced_stage or transcript is None:
                transcript, transcript_path = transcribe_audio(audio_path, config, context)
            elif transcript_path is None:
                transcript_path = prepared.get("transcript_path") or artifacts.get("transcript_raw")
                transcript_path = _ensure_path(transcript_path)
            if transcript_path is None:
                raise RuntimeError("Transcription stage could not resolve transcript path.")
            artifacts["transcript_raw"] = str(transcript_path)
            stages.append({"name": "transcribe", "segments": len(transcript.get("segments", []))})

        elif stage_name == "normalize":
            if transcript is None:
                if transcript_path is None:
                    raise RuntimeError("Normalization requires transcript data.")
                transcript = _load_json_file(transcript_path, "transcribe")
            if forced_stage or normalized_transcript is None:
                normalized_transcript, normalized_path = normalize_transcript(transcript, config, context)
            elif normalized_path is None:
                normalized_path = prepared.get("normalized_path") or artifacts.get("transcript_normalized")
                normalized_path = _ensure_path(normalized_path)
            if normalized_path is None:
                raise RuntimeError("Normalization stage could not resolve normalized transcript path.")
            artifacts["transcript_normalized"] = str(normalized_path)
            stages.append({"name": "normalize", "segments": len(normalized_transcript.get("segments", []))})

        elif stage_name == "segment":
            if transcript is None:
                if transcript_path is None:
                    raise RuntimeError("Segmentation requires transcript data.")
                transcript = _load_json_file(transcript_path, "transcribe")
            if normalized_transcript is None:
                if normalized_path is None:
                    raise RuntimeError("Segmentation requires normalized transcript data.")
                normalized_transcript = _load_json_file(normalized_path, "normalize")
            if forced_stage or segmented_transcript is None:
                segmented_transcript, segmented_path = split_transcript_segments(normalized_transcript, config, context)
            elif segmented_path is None:
                segmented_path = prepared.get("segments_path") or artifacts.get("transcript")
                segmented_path = _ensure_path(segmented_path)
            if segmented_path is None:
                raise RuntimeError("Segmentation stage could not resolve segments path.")
            artifacts["transcript"] = str(segmented_path)
            stages.append({"name": "segment", "segments": len(segmented_transcript.get("segments", []))})

        elif stage_name == "translate":
            if segmented_transcript is None:
                if segmented_path is None:
                    raise RuntimeError("Translation requires segmented transcript data.")
                segmented_transcript = _load_json_file(segmented_path, "segment")
            segments_input = segmented_transcript.get("segments", [])
            if forced_stage or translated_segments is None:
                translated_segments, translated_path = translate_segments(segments_input, config, context)
            elif translated_path is None:
                translated_path = prepared.get("translated_path") or artifacts.get("translated_segments")
                translated_path = _ensure_path(translated_path)
            if translated_path is None:
                raise RuntimeError("Translation stage could not resolve translated segments path.")
            artifacts["translated_segments"] = str(translated_path)
            stages.append({"name": "translate", "segments": len(translated_segments or [])})

        elif stage_name == "subtitle_source":
            if segmented_transcript is None:
                if segmented_path is None:
                    raise RuntimeError("Source subtitle generation requires segmented transcript data.")
                segmented_transcript = _load_json_file(segmented_path, "segment")
            segments_input = segmented_transcript.get("segments", [])
            if forced_stage or source_subtitle is None:
                source_subtitle = generate_source_subtitles(segments_input, context)
            artifacts["subtitle_source"] = str(source_subtitle)
            stages.append({"name": "subtitle_source", "path": str(source_subtitle)})

        elif stage_name == "subtitle_translated":
            if translated_segments is None:
                if translated_path is None:
                    raise RuntimeError("Translated subtitle generation requires translated segments data.")
                translated_segments = _load_json_file(translated_path, "translate")
            if forced_stage or translated_subtitle is None:
                translated_subtitle = generate_translated_subtitles(translated_segments or [], context)
            artifacts["subtitle_translated"] = str(translated_subtitle)
            stages.append({"name": "subtitle_translated", "path": str(translated_subtitle)})

        elif stage_name == "burn_translated_subtitles":
            if video_path is None:
                raise RuntimeError("Overlay stage requires the source video artifact.")
            if translated_subtitle is None:
                if artifacts.get("subtitle_translated"):
                    translated_subtitle = _ensure_path(artifacts.get("subtitle_translated"))
                if translated_subtitle is None:
                    raise RuntimeError("Overlay stage requires translated subtitle file.")
            if forced_stage or final_video is None:
                final_video = burn_translated_subtitles(
                    video_path,
                    translated_subtitle,
                    config,
                    context,
                )
            artifacts["video_final"] = str(final_video)
            stages.append({"name": "burn_translated_subtitles", "path": str(final_video)})

        else:
            raise ValueError(f"Unhandled pipeline stage '{stage_name}' in execution plan.")

    metadata["stages"] = stages
    metadata["status"] = "completed"
    context.write_metadata(metadata)

    return PipelineResult(
        run_id=context.run_id,
        output_video=str(final_video) if final_video else None,
        context=context,
        artifacts={k: str(v) if not isinstance(v, list) else [str(i) for i in v] for k, v in artifacts.items()},
    )

