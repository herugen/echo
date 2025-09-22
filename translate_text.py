"""
文本翻译任务
使用 DeepSeek 翻译文本片段，并存储结果到 MinIO
"""

import os
import json
import uuid
import requests
import asyncio
from typing import List, Dict, Any, Optional
from minio_storage import get_storage


async def translate_text(segments_data: List[Dict[str, Any]], target_language: str, task_id: str) -> List[Dict[str, Any]]:
    """使用 DeepSeek 翻译文本片段并存储结果到 MinIO"""
    
    try:
        print(f"开始翻译文本到 {target_language}，共 {len(segments_data)} 个片段")
        
        if not segments_data:
            print("没有文本片段需要翻译")
            return segments_data
        
        # 获取 DeepSeek API 配置
        deepseek_api_key = os.getenv("DEEPSEEK_API_KEY")
        deepseek_base_url = os.getenv("DEEPSEEK_BASE_URL", "https://api.deepseek.com/v1")
        
        if not deepseek_api_key:
            print("警告: 未配置 DEEPSEEK_API_KEY，跳过文本翻译")
            return segments_data
        
        # 将片段按文本长度分组，避免单次请求过长
        max_chunk_size = 2000  # 每个块的最大字符数
        chunks = []
        current_chunk = []
        current_size = 0
        
        for segment in segments_data:
            segment_size = len(segment["text"])
            
            # 如果添加当前片段会超过限制，先处理当前块
            if current_size + segment_size > max_chunk_size and current_chunk:
                chunks.append(current_chunk)
                current_chunk = [segment]
                current_size = segment_size
            else:
                current_chunk.append(segment)
                current_size += segment_size
        
        # 添加最后一个块
        if current_chunk:
            chunks.append(current_chunk)
        
        print(f"将文本分为 {len(chunks)} 个块进行翻译")
        
        # 处理每个块
        translated_segments = []
        
        for chunk_idx, chunk in enumerate(chunks):
            print(f"翻译第 {chunk_idx + 1}/{len(chunks)} 个块，包含 {len(chunk)} 个片段")
            
            # 构建上下文信息
            context_text = build_translation_context_for_chunk(chunk, segments_data, target_language)
            
            # 调用 DeepSeek API 翻译文本
            translated_text = await call_deepseek_translation_api(
                context_text, 
                deepseek_api_key, 
                deepseek_base_url,
                target_language
            )
            
            if translated_text:
                # 将翻译后的文本重新分配到对应的片段
                translated_chunk = distribute_translated_text(chunk, translated_text)
                translated_segments.extend(translated_chunk)
            else:
                # 如果翻译失败，保持原文本
                translated_segments.extend(chunk)
            
            # 添加延迟避免API限制
            if chunk_idx < len(chunks) - 1:
                await asyncio.sleep(1)
        
        print(f"文本翻译完成，处理了 {len(translated_segments)} 个片段")
        
        # 将结果存储到 MinIO
        storage = get_storage()
        result_filename = f"translated_text_{uuid.uuid4().hex}.json"
        result_json = json.dumps(translated_segments, ensure_ascii=False, indent=2)
        
        object_path = storage.upload_data(
            task_id=task_id,
            step="translate_text",
            data=result_json.encode('utf-8'),
            object_name=result_filename
        )
        
        print(f"文本翻译结果已存储到 MinIO: {object_path}")
        return translated_segments
        
    except Exception as e:
        error_msg = f"文本翻译失败: {str(e)}"
        print(error_msg)
        # 翻译失败时返回原始数据
        return segments_data


def build_translation_context_for_chunk(chunk: List[Dict[str, Any]], all_segments: List[Dict[str, Any]], target_language: str) -> str:
    """为翻译文本块构建上下文信息"""
    
    # 获取当前块的前后片段作为上下文
    chunk_start_idx = all_segments.index(chunk[0]) if chunk[0] in all_segments else 0
    chunk_end_idx = chunk_start_idx + len(chunk) - 1
    
    # 获取前后各2个片段作为上下文
    context_before = all_segments[max(0, chunk_start_idx - 2):chunk_start_idx]
    context_after = all_segments[chunk_end_idx + 1:min(len(all_segments), chunk_end_idx + 3)]
    
    # 构建上下文文本
    context_parts = []
    
    # 添加语言信息
    language_names = {
        "zh": "中文",
        "en": "英文", 
        "ja": "日文",
        "ko": "韩文",
        "fr": "法文",
        "de": "德文",
        "es": "西班牙文",
        "ru": "俄文"
    }
    target_lang_name = language_names.get(target_language, target_language)
    
    context_parts.append(f"请将以下文本翻译成{target_lang_name}，保持原文的语气和语调。")
    
    if context_before:
        context_parts.append("\n前文上下文:")
        for seg in context_before:
            context_parts.append(f"[{seg['start']:.3f}s-{seg['end']:.3f}s] {seg['text']}")
    
    context_parts.append("\n需要翻译的文本片段:")
    for seg in chunk:
        context_parts.append(f"[{seg['start']:.3f}s-{seg['end']:.3f}s] {seg['text']}")
    
    if context_after:
        context_parts.append("\n后文上下文:")
        for seg in context_after:
            context_parts.append(f"[{seg['start']:.3f}s-{seg['end']:.3f}s] {seg['text']}")
    
    return "\n".join(context_parts)


async def call_deepseek_translation_api(context_text: str, api_key: str, base_url: str, target_language: str) -> Optional[str]:
    """调用 DeepSeek API 进行文本翻译"""
    
    prompt = f"""你是一个专业的翻译助手。请将以下文本翻译成目标语言，保持原文的语气、语调和表达方式。

翻译要求：
1. 保持时间戳信息不变
2. 根据上下文语境选择最合适的翻译
3. 保持原文的语言风格和语调
4. 确保翻译自然流畅，符合目标语言的表达习惯
5. 如果是口语化内容，翻译后也要保持口语化特点

请只返回翻译后的文本片段，不要包含时间戳信息，每个片段占一行。

{context_text}

翻译后的文本："""

    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json"
    }
    
    payload = {
        "model": "deepseek-chat",
        "messages": [
            {
                "role": "user",
                "content": prompt
            }
        ],
        "temperature": 0.3,  # 稍高的温度保持翻译的灵活性
        "max_tokens": 4000
    }
    
    try:
        response = requests.post(
            f"{base_url}/chat/completions",
            headers=headers,
            json=payload,
            timeout=30
        )
        
        if response.status_code == 200:
            result = response.json()
            translated_text = result["choices"][0]["message"]["content"].strip()
            print(f"DeepSeek 翻译 API 调用成功，返回文本长度: {len(translated_text)}")
            return translated_text
        else:
            print(f"DeepSeek 翻译 API 调用失败，状态码: {response.status_code}")
            return None
            
    except Exception as e:
        print(f"调用 DeepSeek 翻译 API 时出错: {str(e)}")
        return None


def distribute_translated_text(original_chunk: List[Dict[str, Any]], translated_text: str) -> List[Dict[str, Any]]:
    """将翻译后的文本重新分配到对应的片段"""
    
    # 按行分割翻译后的文本
    translated_lines = [line.strip() for line in translated_text.split('\n') if line.strip()]
    
    translated_segments = []
    
    # 如果翻译后的行数与原片段数相同，直接对应
    if len(translated_lines) == len(original_chunk):
        for i, segment in enumerate(original_chunk):
            translated_segment = segment.copy()
            translated_segment["text"] = translated_lines[i]
            translated_segments.append(translated_segment)
    else:
        # 如果行数不匹配，尝试智能分配
        print(f"警告: 翻译后文本行数({len(translated_lines)})与原片段数({len(original_chunk)})不匹配")
        
        # 按比例分配或保持原文本
        if len(translated_lines) > 0:
            # 简单策略：将翻译后的文本合并后重新分配
            merged_text = " ".join(translated_lines)
            # 按原片段的长度比例分配
            total_original_length = sum(len(seg["text"]) for seg in original_chunk)
            
            current_pos = 0
            for segment in original_chunk:
                segment_ratio = len(segment["text"]) / total_original_length
                segment_length = int(len(merged_text) * segment_ratio)
                
                translated_segment = segment.copy()
                translated_segment["text"] = merged_text[current_pos:current_pos + segment_length].strip()
                translated_segments.append(translated_segment)
                
                current_pos += segment_length
        else:
            # 如果翻译失败，保持原文本
            translated_segments = original_chunk
    
    return translated_segments
