"""
文本翻译任务
使用 DeepSeek 翻译文本片段，并存储结果到 MinIO
"""

import os
import json
import uuid
import requests
import asyncio
import re
from typing import List, Dict, Any, Optional
from minio_storage import get_storage


async def translate_text(segments_data: List[Dict[str, Any]], target_language: str, task_id: str) -> List[Dict[str, Any]]:
    """使用 DeepSeek 翻译文本片段并存储结果到 MinIO"""
    
    try:
        print(f"开始翻译文本到 {target_language}，共 {len(segments_data)} 个片段")
        
        if not segments_data:
            print("没有文本片段需要翻译")
            return segments_data

        clean_segments_data = clean_segments(segments_data)

        # 获取 DeepSeek API 配置
        deepseek_api_key = os.getenv("DEEPSEEK_API_KEY")
        deepseek_base_url = os.getenv("DEEPSEEK_BASE_URL", "https://api.deepseek.com/v1")
        
        if not deepseek_api_key:
            print("警告: 未配置 DEEPSEEK_API_KEY，跳过文本翻译")
            return clean_segments_data
        

        # 将片段按文本长度分组，避免单次请求过长
        max_chunk_size = 1000  # 每个块的最大字符数
        chunks = []
        current_chunk = []
        current_size = 0
        
        for segment in clean_segments_data:
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
            
            
            # 调用 DeepSeek API 翻译文本
            translated_text = await call_deepseek_translation_api(
                chunk, 
                deepseek_api_key, 
                deepseek_base_url,
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
        
    except (ValueError, KeyError, TypeError, requests.RequestException) as e:
        error_msg = f"文本翻译失败: {str(e)}"
        print(error_msg)
        # 翻译失败时返回原始数据
        return clean_segments_data



async def call_deepseek_translation_api(chunk: List[Dict[str, Any]], api_key: str, base_url: str) -> Optional[str]:
    """调用 DeepSeek API 进行文本翻译"""

    
    # 构建更详细的上下文
    context_parts = []
    context_parts.append("请将以下文本翻译成中文，保持原文的语气和语调。")
    context_parts.append("\n重要：必须确保每一行原文对应一行翻译结果，行数必须完全匹配！")
    context_parts.append(f"\n原文共有 {len(chunk)} 行，请确保翻译结果也是 {len(chunk)} 行。")
    context_parts.append("\n需要翻译的文本片段:")
    
    for i, seg in enumerate(chunk):
        context_parts.append(f"\n第{i+1}行: {seg['text']}")
    
    context_text = "".join(context_parts)

    prompt = f"""你是一个专业的翻译助手。请严格按照要求翻译以下文本。

翻译要求：
1. 必须逐行翻译，原文有多少行，翻译结果就必须有多少行
2. 原文有 {len(chunk)} 行，翻译结果也必须是 {len(chunk)} 行
3. 每行翻译结果占一行，不要添加编号、序号或其他格式
4. 保持原文的语言风格和语调
5. 不要合并行，不要拆分行

{context_text}

翻译后的文本（必须 {len(chunk)} 行）："""

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
        #print(f"调用 DeepSeek 翻译 API: {prompt}")
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
            #print(f"翻译后的文本: {translated_text}")
            return translated_text
        else:
            print(f"DeepSeek 翻译 API 调用失败，状态码: {response.status_code}")
            return None
            
    except (requests.RequestException, KeyError, ValueError) as e:
        print(f"调用 DeepSeek 翻译 API 时出错: {str(e)}")
        return None


def distribute_translated_text(original_chunk: List[Dict[str, Any]], translated_text: str) -> List[Dict[str, Any]]:
    """将翻译后的文本重新分配到对应的片段"""
    
    # 按行分割翻译后的文本
    translated_lines = [line.strip() for line in translated_text.split('\n') if line.strip()]
    
    # 清理翻译后的文本，删除"第X行："前缀
    cleaned_lines = []
    for line in translated_lines:
        # 检查是否以"第X行："开头，如果是则删除前缀
        # 匹配"第X行："或"第X行:"等变体，支持中英文冒号
        pattern = r'^第\d+行[：:]\s*'
        cleaned_line = re.sub(pattern, '', line)
        cleaned_lines.append(cleaned_line)
    
    translated_segments = []
    
    # 如果翻译后的行数与原片段数相同，直接对应
    if len(cleaned_lines) == len(original_chunk):
        for i, segment in enumerate(original_chunk):
            translated_segment = segment.copy()
            translated_segment["text"] = cleaned_lines[i]
            translated_segments.append(translated_segment)
    else:
        # 如果行数不匹配，尝试智能分配
        print(f"警告: 翻译后文本行数({len(cleaned_lines)})与原片段数({len(original_chunk)})不匹配")
        print(f"翻译后的文本: {cleaned_lines}")
        print(f"原片段: {json.dumps(original_chunk, ensure_ascii=False, indent=2)}")
        translated_segments = original_chunk
    return translated_segments


def clean_segments(segments_data: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """清理文本片段"""
    new_segments_data = []
    for segment in segments_data:
        new_segments_data.append({
            "start": segment["start"],
            "end": segment["end"],
            "text": segment["text"]
        })
    return new_segments_data