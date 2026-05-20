from __future__ import annotations

import json
import os
import site
import sys
from abc import ABC, abstractmethod
from pathlib import Path
from typing import Any

from echo_engine.adapters.media import ensure_ffmpeg_cli_on_path
from echo_engine.domain.transcript import Transcript, TranscriptSegment


_CUDA_DLL_DIRECTORY_HANDLES: list[Any] = []
_CUDA_DLL_DIRECTORIES: set[str] = set()


def configure_cuda_dll_search_path() -> list[str]:
    if sys.platform != "win32":
        return []

    site_roots = [Path(sys.prefix) / "Lib" / "site-packages"]
    try:
        site_roots.extend(Path(path) for path in site.getsitepackages())
    except Exception:
        pass
    try:
        site_roots.append(Path(site.getusersitepackages()))
    except Exception:
        pass

    bin_dirs: list[Path] = []
    for root in dict.fromkeys(site_roots):
        nvidia_root = root / "nvidia"
        if not nvidia_root.exists():
            continue
        bin_dirs.extend(path for path in nvidia_root.glob("*/bin") if path.is_dir())

    added: list[str] = []
    path_entries = os.environ.get("PATH", "").split(os.pathsep) if os.environ.get("PATH") else []
    for bin_dir in dict.fromkeys(bin_dirs):
        value = str(bin_dir)
        if value not in _CUDA_DLL_DIRECTORIES and hasattr(os, "add_dll_directory"):
            _CUDA_DLL_DIRECTORY_HANDLES.append(os.add_dll_directory(value))
            _CUDA_DLL_DIRECTORIES.add(value)
        if value not in path_entries:
            path_entries.insert(0, value)
        added.append(value)
    if path_entries:
        os.environ["PATH"] = os.pathsep.join(path_entries)
    return added


def detect_whisperx_runtime() -> tuple[str, str, dict[str, Any]]:
    diagnostics: dict[str, Any] = {
        "cuda_dll_dirs": configure_cuda_dll_search_path(),
    }
    try:
        import torch

        diagnostics["torch_version"] = torch.__version__
        diagnostics["torch_cuda_version"] = torch.version.cuda
        diagnostics["cuda_available"] = torch.cuda.is_available()
        if torch.cuda.is_available():
            try:
                diagnostics["cuda_device_name"] = torch.cuda.get_device_name(0)
            except Exception as error:
                diagnostics["cuda_device_name_error"] = str(error)
            return "cuda", "float16", diagnostics
    except Exception as error:
        diagnostics["cuda_detection_error"] = str(error)
    return "cpu", "int8", diagnostics


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
        detected_device, detected_compute_type, diagnostics = detect_whisperx_runtime()
        self.device = detected_device if device == "auto" else device
        self.compute_type = detected_compute_type if compute_type == "auto" else compute_type
        self.batch_size = batch_size
        self.download_root = download_root
        self.diagnostics = diagnostics
        self.fallback_reason: str | None = None

    def runtime_info(self) -> dict[str, Any]:
        return {
            "backend": "whisperx",
            "model": self.model_name,
            "device": self.device,
            "compute_type": self.compute_type,
            "batch_size": self.batch_size,
            "fallback_reason": self.fallback_reason,
            **self.diagnostics,
        }

    def transcribe(self, audio_path: Path) -> Transcript:
        ensure_ffmpeg_cli_on_path()
        configure_cuda_dll_search_path()
        import whisperx

        try:
            result = self._transcribe_with_runtime(whisperx, audio_path)
        except Exception as error:
            if self.device != "cuda":
                raise
            self.fallback_reason = str(error)
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
