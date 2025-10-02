"""Main pipeline orchestrator."""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Dict, List, Optional

from .config import PipelineConfig
from .context import PipelineContext
from .stages import (
    download_video,
    probe_video_format,
    extract_audio_track,
    transcribe_audio,
    split_transcript_segments,
    translate_segments,
    generate_source_subtitles,
    generate_translated_subtitles,
    burn_translated_subtitles,
)


@dataclass
class PipelineResult:
    run_id: str
    output_video: Optional[str]
    context: PipelineContext
    artifacts: Dict[str, str]


def run_pipeline(config: PipelineConfig) -> PipelineResult:
    """Run the translation pipeline synchronously based on configuration."""

    context = PipelineContext.create(
        workdir=config.workdir,
        job_name=config.job_name or "video-translation",
        source_identifier=config.source_url or str(config.local_video),
    )
    context.ensure_dirs()

    metadata: Dict[str, object] = {
        "config": {
            "target_language": config.target_language,
            "source_url": config.source_url,
            "local_video": str(config.local_video) if config.local_video else None,
            "whisper_model": config.whisper_model,
        },
        "artifacts": {},
        "stages": [],
    }

    stages: List[Dict[str, object]] = []

    video_path = download_video(config, context)
    metadata["artifacts"]["video"] = str(video_path)
    stages.append({"name": "download", "path": str(video_path)})

    format_path = probe_video_format(video_path, config, context)
    metadata["artifacts"]["video_format"] = str(format_path)
    stages.append({"name": "probe_video", "path": str(format_path)})

    audio_path = extract_audio_track(video_path, config, context)
    metadata["artifacts"]["audio"] = str(audio_path)
    stages.append({"name": "extract_audio", "path": str(audio_path)})

    transcript, transcript_path = transcribe_audio(audio_path, config, context)
    metadata["artifacts"]["transcript_raw"] = str(transcript_path)
    stages.append({"name": "transcribe", "segments": len(transcript.get("segments", []))})

    segmented_transcript, segmented_path = split_transcript_segments(transcript, config, context)
    metadata["artifacts"]["transcript"] = str(segmented_path)
    stages.append({"name": "segment", "segments": len(segmented_transcript.get("segments", []))})

    translated_segments, translated_path = translate_segments(segmented_transcript.get("segments", []), config, context)
    metadata["artifacts"]["translated_segments"] = str(translated_path)
    stages.append({"name": "translate", "segments": len(translated_segments)})

    source_subtitle = generate_source_subtitles(segmented_transcript.get("segments", []), context)
    metadata["artifacts"]["subtitle_source"] = str(source_subtitle)
    stages.append({"name": "subtitle_source", "path": str(source_subtitle)})

    translated_subtitle = generate_translated_subtitles(translated_segments, context)
    metadata["artifacts"]["subtitle_translated"] = str(translated_subtitle)
    stages.append({"name": "subtitle_translated", "path": str(translated_subtitle)})

    final_video = burn_translated_subtitles(
        video_path,
        translated_subtitle,
        config,
        context,
    )
    metadata["artifacts"]["video_final"] = str(final_video)
    stages.append({"name": "burn_translated_subtitles", "path": str(final_video)})

    metadata["stages"] = stages

    metadata["status"] = "completed"
    context.write_metadata(metadata)

    return PipelineResult(
        run_id=context.run_id,
        output_video=str(final_video),
        context=context,
        artifacts={k: str(v) if not isinstance(v, list) else [str(i) for i in v] for k, v in metadata["artifacts"].items()},
    )

