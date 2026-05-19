from __future__ import annotations

import json
import re
import urllib.error
import urllib.request
from abc import ABC, abstractmethod
from pathlib import Path

from echo_engine.domain.transcript import Transcript
from echo_engine.domain.translation import Translation, TranslationSegment


class TranslatorAdapter(ABC):
    @abstractmethod
    def translate(self, transcript: Transcript, target_language: str) -> Translation:
        raise NotImplementedError


class DeepSeekTranslatorAdapter(TranslatorAdapter):
    default_model = "deepseek-v4-pro"
    batch_size = 24

    def __init__(self, base_url: str, api_key: str, model: str | None = None) -> None:
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key
        self.model = model or self.default_model

    def translate(self, transcript: Transcript, target_language: str) -> Translation:
        if not self.api_key:
            raise ValueError("DeepSeek API key is not configured")

        source_texts = [segment.text for segment in transcript.segments]
        translated_texts = self._translate_texts(
            source_texts,
            target_language,
        )
        if len(translated_texts) != len(source_texts):
            translated_texts = self._translate_individually(source_texts, target_language)

        return Translation(
            source_language=transcript.language,
            target_language=target_language,
            segments=[
                TranslationSegment(
                    start=segment.start,
                    end=segment.end,
                    source_text=segment.text,
                    translated_text=translated,
                )
                for segment, translated in zip(transcript.segments, translated_texts)
            ],
        )

    def _translate_texts(self, texts: list[str], target_language: str) -> list[str]:
        if not texts:
            return []

        translated: list[str] = []
        for index in range(0, len(texts), self.batch_size):
            batch = texts[index : index + self.batch_size]
            translated.extend(self._translate_batch(batch, target_language))
        if len(translated) != len(texts):
            return self._translate_individually(texts, target_language)
        return translated

    def _translate_batch(self, texts: list[str], target_language: str) -> list[str]:
        if not texts:
            return []
        if len(texts) == 1:
            return [self._translate_single(texts[0], target_language)]

        content = self._chat_completion(
            [
                {
                    "role": "system",
                    "content": (
                        "You are a subtitle translation engine. "
                        "Return machine-readable JSON only. Do not use markdown."
                    ),
                },
                {
                    "role": "user",
                    "content": (
                        f"Translate every item into {target_language}.\n"
                        "Preserve the exact number of items and the exact id for each item.\n"
                        "Return JSON in this exact shape: "
                        '{"translations":[{"id":0,"text":"translated text"}]}.\n\n'
                        + json.dumps(
                            {"items": [{"id": i, "text": text} for i, text in enumerate(texts)]},
                            ensure_ascii=False,
                        )
                    ),
                },
            ]
        )
        parsed = self._parse_translation_json(content, len(texts))
        if len(parsed) == len(texts):
            return parsed

        return self._translate_individually(texts, target_language)

    def _translate_individually(self, texts: list[str], target_language: str) -> list[str]:
        return [self._translate_single(text, target_language) for text in texts]

    def _translate_single(self, text: str, target_language: str) -> str:
        if not text.strip():
            return ""
        content = self._chat_completion(
            [
                {
                    "role": "system",
                    "content": "You are a subtitle translation engine. Return only the translated subtitle text.",
                },
                {
                    "role": "user",
                    "content": f"Translate this subtitle into {target_language}:\n{text}",
                },
            ]
        )
        return self._clean_plain_text(content) or text

    def _chat_completion(self, messages: list[dict[str, str]]) -> str:
        payload = {
            "model": self.model,
            "messages": messages,
            "temperature": 0,
        }
        request = urllib.request.Request(
            f"{self.base_url}/chat/completions",
            data=json.dumps(payload).encode("utf-8"),
            headers={
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json",
            },
            method="POST",
        )
        try:
            with urllib.request.urlopen(request, timeout=120) as response:
                data = json.loads(response.read().decode("utf-8"))
        except urllib.error.HTTPError as error:
            body = error.read().decode("utf-8", errors="replace")
            raise RuntimeError(f"DeepSeek request failed: HTTP {error.code}: {body}") from error
        return str(data["choices"][0]["message"]["content"]).strip()

    def _parse_translation_json(self, content: str, expected_count: int) -> list[str]:
        data = self._loads_json_fragment(content)
        if data is None:
            return []

        values = data.get("translations") if isinstance(data, dict) else data
        if isinstance(values, list):
            if all(isinstance(item, str) for item in values):
                return [item.strip() for item in values] if len(values) == expected_count else []
            by_id: dict[int, str] = {}
            for item in values:
                if not isinstance(item, dict):
                    continue
                try:
                    item_id = int(item.get("id"))
                except (TypeError, ValueError):
                    continue
                text = item.get("text") or item.get("translation") or item.get("translated_text")
                if isinstance(text, str):
                    by_id[item_id] = text.strip()
            if all(index in by_id for index in range(expected_count)):
                return [by_id[index] for index in range(expected_count)]

        if isinstance(values, dict):
            result: list[str] = []
            for index in range(expected_count):
                value = values.get(str(index), values.get(index))
                if not isinstance(value, str):
                    return []
                result.append(value.strip())
            return result

        return []

    def _loads_json_fragment(self, content: str):
        candidates = [content.strip()]
        fenced = re.search(r"```(?:json)?\\s*(.*?)```", content, flags=re.DOTALL | re.IGNORECASE)
        if fenced:
            candidates.append(fenced.group(1).strip())
        for opening, closing in [("{", "}"), ("[", "]")]:
            start = content.find(opening)
            end = content.rfind(closing)
            if start != -1 and end > start:
                candidates.append(content[start : end + 1])

        for candidate in candidates:
            try:
                return json.loads(candidate)
            except json.JSONDecodeError:
                continue
        return None

    def _clean_plain_text(self, content: str) -> str:
        text = content.strip()
        fenced = re.fullmatch(r"```(?:text)?\\s*(.*?)```", text, flags=re.DOTALL | re.IGNORECASE)
        if fenced:
            text = fenced.group(1).strip()
        return text.strip().strip('"').strip()


class JsonTranslationStore:
    def write(self, translation: Translation, output_path: Path) -> Path:
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(json.dumps(translation.to_dict(), ensure_ascii=False, indent=2), encoding="utf-8")
        return output_path
