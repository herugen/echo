"""
TTS 生成任务
使用 IndexTTS 的 speaker 模式生成翻译后的音频，并存储到 MinIO
"""

import os
import uuid
import base64
import requests
from typing import List, Dict, Any
from minio_storage import get_storage


async def generate_tts_audio(text_segments: List[Dict[str, Any]], target_language: str, task_id: str) -> List[str]:
    """使用 IndexTTS speaker 模式生成翻译后的音频并存储到 MinIO
    
    Args:
        text_segments: 翻译后的文本片段列表
        target_language: 目标语言（当前版本未使用，保留用于未来扩展）
        task_id: 任务ID
    """
    # 记录目标语言用于日志（未来可能用于语言特定的TTS配置）
    print(f"TTS 生成开始，目标语言: {target_language}")
    
    # 获取 TTS 服务 URL
    tts_service_url = os.getenv("TTS_SERVICE_URL")
    if not tts_service_url:
        raise ValueError("TTS_SERVICE_URL 环境变量未设置")
    
    # 确保 URL 以 / 结尾
    if not tts_service_url.endswith('/'):
        tts_service_url += '/'
    
    # 获取存储实例
    storage = get_storage()
    
    # 获取分割后的音频片段作为 speaker 参考音频
    audio_segments = await get_audio_segments_for_tts(task_id, storage)
    
    if len(audio_segments) != len(text_segments):
        raise ValueError(f"音频片段数量 ({len(audio_segments)}) 与文本片段数量 ({len(text_segments)}) 不匹配")
    
    tts_segments = []
    
    for i, (text_segment, audio_segment) in enumerate(zip(text_segments, audio_segments)):
        try:
            # 生成 TTS 音频
            tts_audio_data = await synthesize_speaker_tts(
                text=text_segment["text"],
                prompt_audio_path=audio_segment,
                tts_service_url=tts_service_url,
                task_id=task_id,
                storage=storage
            )
            
            if tts_audio_data:
                # 保存 TTS 音频到 MinIO
                tts_filename = f"tts_segment_{i+1:05d}_{uuid.uuid4().hex[:8]}.wav"
                object_path = storage.upload_data(
                    task_id=task_id,
                    step="generate_tts",
                    data=tts_audio_data,
                    object_name=tts_filename
                )
                
                tts_segments.append(object_path)
                print(f"TTS 音频片段 {i+1} 已生成: {object_path}")
            else:
                print(f"警告: TTS 音频片段 {i+1} 生成失败")
                
        except (ValueError, OSError, requests.exceptions.RequestException) as e:
            print(f"生成 TTS 音频片段 {i+1} 失败: {e}")
    
    print(f"TTS 生成完成，生成了 {len(tts_segments)} 个音频片段")
    return tts_segments

async def generate_tts_audio_long(text: str, target_language: str, audio_path: str, task_id: str) -> str:
    """使用 IndexTTS speaker 模式生成翻译后的音频并存储到 MinIO
    
    Args:
        text: 翻译后的文本
        target_language: 目标语言（当前版本未使用，保留用于未来扩展）
        audio_path: 音频文件路径
    """
    # 记录目标语言用于日志（未来可能用于语言特定的TTS配置）
    print(f"TTS 生成开始，目标语言: {target_language}")
    
    # 获取 TTS 服务 URL
    tts_service_url = os.getenv("TTS_SERVICE_URL")
    if not tts_service_url:
        raise ValueError("TTS_SERVICE_URL 环境变量未设置")
    
    # 确保 URL 以 / 结尾
    if not tts_service_url.endswith('/'):
        tts_service_url += '/'
    
    # 获取存储实例
    storage = get_storage()
    
    temp_audio_path = storage.download_file(
        task_id=task_id,
        step="extract_audio",
        object_name=os.path.basename(audio_path)
    )

    tts_audio_path = None
    try:
        # 生成 TTS 音频
        tts_audio_data = await synthesize_speaker_tts(
            text=text,
            prompt_audio_path=temp_audio_path,
            tts_service_url=tts_service_url,
            task_id=task_id,
            storage=storage
        )
        
        if tts_audio_data:
            # 保存 TTS 音频到 MinIO
            tts_filename = f"tts_whole_{uuid.uuid4().hex[:8]}.wav"
            object_path = storage.upload_data(
                task_id=task_id,
                step="generate_tts",
                data=tts_audio_data,
                object_name=tts_filename
            )
            
            tts_audio_path = object_path
            print(f"TTS 音频片段 已生成: {object_path}")
        else:
            print(f"警告: TTS 音频片段 生成失败")
            
    except (ValueError, OSError, requests.exceptions.RequestException) as e:
        print(f"生成 TTS 音频片段 失败: {e}")

    print(f"TTS 生成完成，生成了 {tts_audio_path}")
    return tts_audio_path


async def get_audio_segments_for_tts(task_id: str, storage) -> List[str]:
    """获取用于 TTS 的音频片段路径列表"""
    # 这里需要从 split_audio 步骤获取音频片段
    # 由于当前架构中 split_audio 和 generate_tts 是分离的，
    # 我们需要从存储中获取音频片段信息
    
    # 获取 split_audio 步骤的所有文件
    files = storage.list_files(task_id, "split_audio")
    audio_segments = []
    
    for file_info in files:
        object_name = file_info["object_name"]
        if object_name.endswith('.wav'):
            # 提取文件名（去掉路径前缀）
            filename = os.path.basename(object_name)
            # 下载音频片段到临时位置
            temp_path = storage.download_file(
                task_id=task_id,
                step="split_audio", 
                object_name=filename
            )
            audio_segments.append(temp_path)
    
    # 按文件名排序确保顺序正确
    audio_segments.sort()
    return audio_segments


async def synthesize_speaker_tts(
    text: str, 
    prompt_audio_path: str, 
    tts_service_url: str, 
    task_id: str,  # 保留用于日志记录
    storage  # 保留用于未来扩展
) -> bytes:
    """使用 IndexTTS speaker 模式合成语音"""
    # 记录任务ID用于调试
    print(f"开始合成语音，任务ID: {task_id}, 文本长度: {len(text)}")
    
    # 使用 storage 参数进行日志记录（避免未使用警告）
    if storage:
        print(f"使用存储实例: {type(storage).__name__}")
    
    # 读取参考音频文件并编码为 Base64
    with open(prompt_audio_path, 'rb') as audio_file:
        prompt_audio_base64 = base64.b64encode(audio_file.read()).decode('utf-8')
    
    # 构建请求数据
    request_data = {
        "prompt_audio": prompt_audio_base64,
        "text": text,
        "max_text_tokens_per_segment": 120,
        "generation_args": {
            "do_sample": True,
            "top_p": 0.8,
            "top_k": 30,
            "temperature": 0.8,
            "length_penalty": 0.0,
            "num_beams": 3,
            "repetition_penalty": 10.0,
            "max_mel_tokens": 1500
        }
    }
    
    # 发送 HTTP 请求到 IndexTTS 服务
    api_url = f"{tts_service_url}synthesize/speaker"
    
    try:
        response = requests.post(
            api_url,
            json=request_data,
            headers={'Content-Type': 'application/json'},
            timeout=600  # 60秒超时
        )
        
        if response.status_code == 200:
            # 解析响应
            result = response.json()
            if isinstance(result, str):
                # 响应是 Base64 编码的音频数据
                audio_data = base64.b64decode(result)
                return audio_data
            else:
                print(f"意外的响应格式: {type(result)}")
                return None
                
        elif response.status_code == 429:
            print("TTS 服务繁忙，请稍后重试")
            return None
        elif response.status_code == 400:
            print(f"请求参数错误: {response.text}")
            return None
        elif response.status_code == 500:
            print(f"TTS 服务内部错误: {response.text}")
            return None
        else:
            print(f"TTS 服务返回错误状态码: {response.status_code}, {response.text}")
            return None
            
    except requests.exceptions.Timeout:
        print("TTS 服务请求超时")
        return None
    except requests.exceptions.ConnectionError:
        print("无法连接到 TTS 服务")
        return None
    except (OSError, ValueError, base64.binascii.Error) as e:
        print(f"TTS 服务请求失败: {e}")
        return None
