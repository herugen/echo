"""
TTS 生成任务
使用 IndexTTS 的 speaker 模式生成翻译后的音频，并存储到 MinIO
"""

import os
import uuid
import base64
import requests
import subprocess
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
            )
            if not tts_audio_data:
                print(f"警告: TTS 音频片段 {i+1} 生成失败")
                continue

            duration = text_segment["end"] - text_segment["start"]
            
            # 将 TTS 音频数据写入临时文件以便获取时长
            temp_tts_path = f"/tmp/tts_temp_{uuid.uuid4().hex}.wav"
            temp_stretched_tts_path = f"/tmp/stretched_tts_temp_{uuid.uuid4().hex}.wav"
            with open(temp_tts_path, 'wb') as f:
                f.write(tts_audio_data)
            
            tts_audio_duration = await probe_audio_duration(temp_tts_path)
            await stretch_audio(temp_tts_path, temp_stretched_tts_path, tts_audio_duration, duration)
            
            re_synthesize_tts_data = await synthesize_reference_tts(
                text=text_segment["text"],
                prompt_audio_path=audio_segment,
                reference_audio_path=temp_stretched_tts_path,
                tts_service_url=tts_service_url,
                task_id=task_id,
            )

            # 保存 TTS 音频到 MinIO
            tts_filename = f"tts_segment_{i+1:05d}_{uuid.uuid4().hex[:8]}.wav"
            object_path = storage.upload_data(
                task_id=task_id,
                step="generate_tts",
                data=re_synthesize_tts_data,
                object_name=tts_filename
            )
            
            tts_segments.append(object_path)
            print(f"TTS 音频片段 {i+1} 已生成: {object_path}")
            # 清理临时文件
            os.unlink(temp_tts_path)
            os.unlink(temp_stretched_tts_path)
                
        except (ValueError, OSError, requests.exceptions.RequestException) as e:
            print(f"生成 TTS 音频片段 {i+1} 失败: {e}")
    
    print(f"TTS 生成完成，生成了 {len(tts_segments)} 个音频片段")
    return tts_segments


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
    task_id: str
) -> bytes:
    """使用 IndexTTS speaker 模式合成语音"""
    # 记录任务ID用于调试
    print(f"开始合成语音，任务ID: {task_id}, 文本长度: {len(text)}")
    
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


async def synthesize_reference_tts(
    text: str, 
    prompt_audio_path: str, 
    reference_audio_path: str, 
    tts_service_url: str, 
    task_id: str
) -> bytes:
    """使用 IndexTTS reference 模式合成语音"""
    # 记录任务ID用于调试
    print(f"开始合成语音，任务ID: {task_id}, 文本长度: {len(text)}")
    
    # 读取参考音频文件并编码为 Base64
    with open(prompt_audio_path, 'rb') as audio_file:
        prompt_audio_base64 = base64.b64encode(audio_file.read()).decode('utf-8')
    
    with open(reference_audio_path, 'rb') as audio_file:
        reference_audio_base64 = base64.b64encode(audio_file.read()).decode('utf-8')

    # 构建请求数据
    request_data = {
        "prompt_audio": prompt_audio_base64,
        "text": text,
        "max_text_tokens_per_segment": 120,
        "emotion_audio": reference_audio_base64,
        "emotion_weight": 1.0,
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
    api_url = f"{tts_service_url}synthesize/reference"
    
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

async def probe_audio_duration(audio_path: str) -> float:
    """获取音频文件时长
    
    Args:
        audio_path: 音频文件路径
    """
    cmd = [
        "ffprobe",
        "-v", "quiet",
        "-show_entries", "format=duration",
        "-of", "csv=p=0",
        audio_path
    ]
    
    result = subprocess.run(cmd, capture_output=True, text=True, check=True)
    actual_duration = float(result.stdout.strip())
    
    return actual_duration


async def stretch_audio(tts_audio_path: str, temp_stretched_tts_path: str, tts_audio_duration: float, duration: float):
    """拉伸音频文件
    
    Args:
        tts_audio_path: 音频文件路径
        temp_stretched_tts_path: 拉伸后的音频文件路径
        tts_audio_duration: 音频文件时长
        duration: 目标时长
    """
    # 计算速度比例
    speed_ratio = tts_audio_duration / duration
    
    # FFmpeg atempo 滤镜只支持 0.5 到 2.0 之间的值
    # 如果超出范围，需要使用多个 atempo 滤镜串联
    if speed_ratio < 0.5:
        # 对于小于 0.5 的值，使用多个 atempo 滤镜
        # 例如：0.3 = 0.5 * 0.6，所以使用 atempo=0.5,atempo=0.6
        atempo_filters = []
        remaining_ratio = speed_ratio
        
        while remaining_ratio < 0.5:
            atempo_filters.append("atempo=0.5")
            remaining_ratio *= 2
        
        if remaining_ratio > 1.0:
            atempo_filters.append(f"atempo={remaining_ratio}")
        
        filter_complex = ",".join(atempo_filters)
    elif speed_ratio > 2.0:
        # 对于大于 2.0 的值，使用多个 atempo 滤镜
        atempo_filters = []
        remaining_ratio = speed_ratio
        
        while remaining_ratio > 2.0:
            atempo_filters.append("atempo=2.0")
            remaining_ratio /= 2
        
        if remaining_ratio > 1.0:
            atempo_filters.append(f"atempo={remaining_ratio}")
        
        filter_complex = ",".join(atempo_filters)
    else:
        # 在有效范围内，直接使用
        filter_complex = f"atempo={speed_ratio}"

    cmd = [
        "ffmpeg",
        "-i", tts_audio_path,
        "-filter_complex", filter_complex,
        temp_stretched_tts_path
    ]
    
    try:
        subprocess.run(cmd, capture_output=True, text=True, check=True)
        print(f"音频拉伸成功: {speed_ratio:.4f} -> {filter_complex}")
    except subprocess.CalledProcessError as e:
        print(f"FFmpeg 错误: {e}")
        print(f"命令: {' '.join(cmd)}")
        print(f"错误输出: {e.stderr}")
        raise

    return
