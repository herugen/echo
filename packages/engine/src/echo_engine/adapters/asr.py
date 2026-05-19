from __future__ import annotations

import json
from abc import ABC, abstractmethod
from pathlib import Path

from echo_engine.adapters.media import ensure_ffmpeg_cli_on_path
from echo_engine.domain.transcript import Transcript, TranscriptSegment


def detect_whisperx_runtime() -> tuple[str, str]:
    try:
        import torch

        if torch.cuda.is_available():
            return "cuda", "float16"
    except Exception:
        pass
    return "cpu", "int8"


class AsrAdapter(ABC):
    @abstractmethod
    def transcribe(self, audio_path: Path) -> Transcript:
        raise NotImplementedError


class WhisperXAdapter(AsrAdapter):
    def __init__(
        self,
        model_name: str = "large-v3",
        device: str = "auto",
        compute_type: str = "auto",
        batch_size: int = 4,
        download_root: Path | None = None,
    ) -> None:
        self.model_name = model_name
        detected_device, detected_compute_type = detect_whisperx_runtime()
        self.device = detected_device if device == "auto" else device
        self.compute_type = detected_compute_type if compute_type == "auto" else compute_type
        self.batch_size = batch_size
        self.download_root = download_root

    def runtime_info(self) -> dict[str, str | int]:
        return {
            "backend": "whisperx",
            "model": self.model_name,
            "device": self.device,
            "compute_type": self.compute_type,
            "batch_size": self.batch_size,
        }

    def transcribe(self, audio_path: Path) -> Transcript:
        ensure_ffmpeg_cli_on_path()
        import whisperx

        try:
            result = self._transcribe_with_runtime(whisperx, audio_path)
        except Exception:
            if self.device != "cuda":
                raise
            self.device = "cpu"
            self.compute_type = "int8"
            result = self._transcribe_with_runtime(whisperx, audio_path)
        segments = [
            TranscriptSegment(
                start=round(float(segment.get("start", 0.0)), 3),
                end=round(float(segment.get("end", 0.0)), 3),
                text=str(segment.get("text", "")).strip(),
            )
            for segment in result.get("segments", [])
            if str(segment.get("text", "")).strip()
        ]
        return Transcript(language=str(result.get("language", "unknown")), segments=segments)

    def _transcribe_with_runtime(self, whisperx, audio_path: Path) -> dict:
        model = whisperx.load_model(
            self.model_name,
            self.device,
            compute_type=self.compute_type,
            download_root=str(self.download_root) if self.download_root else None,
        )
        audio = whisperx.load_audio(str(audio_path))
        return model.transcribe(audio, batch_size=self.batch_size)


class JsonTranscriptStore:
    def write(self, transcript: Transcript, output_path: Path) -> Path:
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(
            json.dumps(transcript.to_dict(), ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        return output_path
