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

    prepared_segments: List[Dict] = []
    for segment in segments:
        source_text = (segment.get("source_text") or segment.get("text") or "").strip()
        prepared_segment = dict(segment)
        prepared_segment["source_text"] = source_text
        prepared_segments.append({**prepared_segment, "text": source_text})

    if not config.deepseek_api_key:
        output = context.subpath("translations", "segments.json")
        with output.open("w", encoding="utf-8") as fp:
            json.dump(prepared_segments, fp, ensure_ascii=False, indent=2)
        return prepared_segments, output

    max_chunk_chars = 1000
    chunks: List[List[int]] = []
    current_indices: List[int] = []
    size = 0
    for index, segment in enumerate(prepared_segments):
        length = len(segment.get("source_text", ""))
        if current_indices and size + length > max_chunk_chars:
            chunks.append(current_indices)
            current_indices = [index]
            size = length
        else:
            current_indices.append(index)
            size += length
    if current_indices:
        chunks.append(current_indices)

    for chunk_number, indices in enumerate(chunks, start=1):
        request_payload = [
            {
                "start": prepared_segments[i]["start"],
                "end": prepared_segments[i]["end"],
                "text": prepared_segments[i].get("source_text", ""),
            }
            for i in indices
        ]
        translated_text = _call_deepseek(request_payload, config)
        if translated_text:
            lines = [line.strip() for line in translated_text.split("\n") if line.strip()]
            results: List[str] = []
            for line in lines:
                cleaned = re.sub(r"^第\d+行[：:]\s*", "", line)
                results.append(cleaned)
            if len(results) == len(indices):
                for idx, text in zip(indices, results):
                    prepared_segments[idx]["text"] = text
            # If mismatch we retain source text as translation fallback
        if chunk_number < len(chunks):
            time.sleep(1)

    output = context.subpath("translations", "segments.json")
    with output.open("w", encoding="utf-8") as fp:
        json.dump(prepared_segments, fp, ensure_ascii=False, indent=2)

    return prepared_segments, output


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

