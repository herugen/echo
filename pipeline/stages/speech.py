"""Speech-to-text stage."""

from __future__ import annotations

import json
import shlex
import shutil
import subprocess
import tempfile
from pathlib import Path
from typing import Dict, List, Tuple

from ..config import PipelineConfig
from ..context import PipelineContext


def _build_docker_command(
    audio_path: Path,
    output_dir: Path,
    config: PipelineConfig,
) -> Tuple[list[str], str]:
    cache_dir = config.whisper_cache_dir
    cache_dir.mkdir(parents=True, exist_ok=True)

    container_audio_name = f"input{audio_path.suffix}"
    container_audio_path = f"/work/{container_audio_name}"
    container_output_dir = "/work/output"
    output_dir.mkdir(parents=True, exist_ok=True)

    base_cmd = [
        "docker",
        "run",
        "--rm",
        "-v",
        f"{audio_path}:{container_audio_path}:ro",
        "-v",
        f"{output_dir}:{container_output_dir}",
        "-v",
        f"{cache_dir}:/root/.cache",
    ]

    if config.whisper_docker_args:
        base_cmd.extend(shlex.split(config.whisper_docker_args))

    cmd = base_cmd + [
        config.whisper_docker_image,
        "--model",
        config.whisper_model,
        "--device",
        config.whisper_device,
        "--compute_type",
        config.whisper_compute_type,
        "--batch_size",
        str(config.whisper_batch_size),
        "--output_dir",
        container_output_dir,
        "--output_format",
        "json",
        "--vad_onset",
        str(config.whisper_vad_onset),
        "--vad_offset",
        str(config.whisper_vad_offset),
        "--chunk_size",
        str(config.whisper_vad_chunk_size),
        "--align_model",
        "WAV2VEC2_ASR_LARGE_LV60K_960H",
        "--highlight_words",
        "True",
        container_audio_path,
    ]

    return cmd, "input"


def transcribe_audio(
    audio_path: Path,
    config: PipelineConfig,
    context: PipelineContext,
) -> Tuple[Dict, Path]:
    audio_path = audio_path.resolve()
    tmp_workspace = context.root / "tmp"
    tmp_workspace.mkdir(parents=True, exist_ok=True)
    raw_output_dir = Path(tempfile.mkdtemp(prefix="whisperx-", dir=str(tmp_workspace)))
    transcripts_dir = context.root / "transcripts"
    transcripts_dir.mkdir(parents=True, exist_ok=True)
    final_output = context.subpath("transcripts", "transcript.json")

    cmd, container_stem = _build_docker_command(audio_path, raw_output_dir, config)
    result = subprocess.run(cmd, capture_output=True, text=True)

    if result.returncode != 0:
        raise RuntimeError(
            "WhisperX docker transcription failed:\n"
            f"Command: {' '.join(cmd)}\n"
            f"stdout: {result.stdout}\n"
            f"stderr: {result.stderr}"
        )

    json_path = raw_output_dir / f"{container_stem}.json"

    if not json_path.exists():
        raise FileNotFoundError("WhisperX docker did not produce transcript.json")

    with json_path.open("r", encoding="utf-8") as fp:
        raw = json.load(fp)

    processed_segments: List[Dict[str, object]] = []
    for segment in raw.get("segments", []):
        text = segment.get("text", "").strip()
        if not text:
            continue

        words: List[Dict[str, object]] = []
        for word in segment.get("words", []):
            probability = word.get("probability")
            if probability is None and word.get("score") is not None:
                probability = word["score"]
            words.append(
                {
                    "start": round(float(word.get("start", 0)), 3),
                    "end": round(float(word.get("end", 0)), 3),
                    "word": word.get("word", "").strip(),
                    "probability": round(float(probability), 3)
                    if probability is not None
                    else None,
                }
            )

        processed_segments.append(
            {
                "start": round(float(segment.get("start", 0)), 3),
                "end": round(float(segment.get("end", 0)), 3),
                "text": text,
                "words": words,
            }
        )

    total_duration = (
        round(processed_segments[-1]["end"], 3) if processed_segments else 0.0
    )

    data: Dict[str, object] = {
        "language": raw.get("language", "unknown"),
        "segments": processed_segments,
        "total_segments": len(processed_segments),
        "total_duration": total_duration,
    }

    with final_output.open("w", encoding="utf-8") as fp:
        json.dump(data, fp, ensure_ascii=False, indent=2)

    return data, final_output


