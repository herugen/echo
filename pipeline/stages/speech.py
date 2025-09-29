"""Speech-to-text stage."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Dict, Tuple

import whisperx

from ..config import PipelineConfig
from ..context import PipelineContext


def _load_asr_model(config: PipelineConfig, *, language: str | None = None):
    vad_options = {
        "vad_onset": config.whisper_vad_onset,
        "vad_offset": config.whisper_vad_offset,
        "chunk_size": config.whisper_vad_chunk_size,
    }

    return whisperx.load_model(
        config.whisper_model,
        config.whisper_device,
        compute_type=config.whisper_compute_type,
        asr_options={
            "multilingual": not config.whisper_model.endswith(".en"),
            "max_new_tokens": None,
            "clip_timestamps": "0",
            "hallucination_silence_threshold": None,
            "hotwords": None,
            "suppress_numerals": False,
        },
        language=language,
        vad_method=config.whisper_vad_method,
        vad_options=vad_options,
        threads=4,
    )


def transcribe_audio(
    audio_path: Path,
    config: PipelineConfig,
    context: PipelineContext,
) -> Tuple[Dict, Path]:
    model = _load_asr_model(config)
    audio = whisperx.load_audio(str(audio_path))
    result = model.transcribe(audio, batch_size=config.whisper_batch_size)

    align_model, metadata = whisperx.load_align_model(
        language_code=result["language"],
        device=config.whisper_device,
    )
    aligned = whisperx.align(
        result["segments"],
        align_model,
        metadata,
        audio,
        config.whisper_device,
        return_char_alignments=False,
    )

    segments = []
    for segment in aligned["segments"]:
        text = segment.get("text", "").strip()
        if not text:
            continue
        words = []
        for word in segment.get("words", []):
            words.append(
                {
                    "start": round(word.get("start", 0), 3),
                    "end": round(word.get("end", 0), 3),
                    "word": word.get("word", "").strip(),
                    "probability": round(word.get("probability", 0), 3)
                    if word.get("probability") is not None
                    else None,
                }
            )
        segments.append(
            {
                "start": round(segment.get("start", 0), 3),
                "end": round(segment.get("end", 0), 3),
                "text": text,
                "words": words,
            }
        )

    data: Dict[str, object] = {
        "language": aligned.get("language", "unknown"),
        "segments": segments,
        "total_segments": len(segments),
        "total_duration": round(segments[-1]["end"], 3) if segments else 0,
    }

    output = context.subpath("transcripts", "transcript.json")
    with output.open("w", encoding="utf-8") as fp:
        json.dump(data, fp, ensure_ascii=False, indent=2)

    return data, output

