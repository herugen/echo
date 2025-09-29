"""Translation stage using DeepSeek."""

from __future__ import annotations

import json
import time
import re
from pathlib import Path
from typing import Dict, List, Tuple

import requests

from ..config import PipelineConfig
from ..context import PipelineContext


def translate_segments(
    segments: List[Dict],
    config: PipelineConfig,
    context: PipelineContext,
) -> Tuple[List[Dict], Path]:
    if not segments:
        return [], context.subpath("translations", "segments.json")

    if not config.deepseek_api_key:
        output = context.subpath("translations", "segments.json")
        with output.open("w", encoding="utf-8") as fp:
            json.dump(segments, fp, ensure_ascii=False, indent=2)
        return segments, output

    cleaned_segments = [
        {"start": s["start"], "end": s["end"], "text": s["text"]}
        for s in segments
    ]

    max_chunk_chars = 1000
    chunks: List[List[Dict]] = []
    current: List[Dict] = []
    size = 0
    for segment in cleaned_segments:
        length = len(segment["text"])
        if current and size + length > max_chunk_chars:
            chunks.append(current)
            current = [segment]
            size = length
        else:
            current.append(segment)
            size += length
    if current:
        chunks.append(current)

    translated: List[Dict] = []
    for idx, chunk in enumerate(chunks, start=1):
        translated_text = _call_deepseek(chunk, config)
        if not translated_text:
            translated.extend(chunk)
            continue
        lines = [line.strip() for line in translated_text.split("\n") if line.strip()]
        results: List[str] = []
        for line in lines:
            cleaned = re.sub(r"^第\d+行[：:]\s*", "", line)
            results.append(cleaned)
        if len(results) != len(chunk):
            translated.extend(chunk)
            continue
        for segment, text in zip(chunk, results):
            translated.append({**segment, "text": text})
        if idx < len(chunks):
            time.sleep(1)

    output = context.subpath("translations", "segments.json")
    with output.open("w", encoding="utf-8") as fp:
        json.dump(translated, fp, ensure_ascii=False, indent=2)

    return translated, output


def _call_deepseek(chunk: List[Dict], config: PipelineConfig) -> str:
    headers = {
        "Authorization": f"Bearer {config.deepseek_api_key}",
        "Content-Type": "application/json",
    }
    prompt_lines = [
        "请将以下文本翻译成中文，保持原文的语气和语调。",
        "重要：必须确保每行原文对应一行翻译结果，行数必须完全匹配。",
        f"原文共有 {len(chunk)} 行，请确保翻译结果也是 {len(chunk)} 行。",
        "需要翻译的文本片段:",
    ]
    for i, segment in enumerate(chunk, start=1):
        prompt_lines.append(f"第{i}行: {segment['text']}")
    prompt = "\n".join(prompt_lines)

    payload = {
        "model": "deepseek-chat",
        "messages": [
            {
                "role": "user",
                "content": prompt,
            }
        ],
        "temperature": 0.3,
        "max_tokens": 4000,
    }

    response = requests.post(
        f"{config.deepseek_base_url}/chat/completions",
        headers=headers,
        json=payload,
        timeout=30,
    )
    if response.status_code != 200:
        return ""
    data = response.json()
    return data["choices"][0]["message"]["content"].strip()

