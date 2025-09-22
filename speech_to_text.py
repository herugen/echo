"""
语音识别任务
使用 WhisperX 进行语音识别，支持对齐和说话人分离，并存储结果到 MinIO
"""

import os
import json
import uuid
from typing import Dict, Any
import whisperx
from minio_storage import get_storage


async def speech_to_text(audio_path: str, task_id: str) -> Dict[str, Any]:
    """使用 WhisperX 进行语音识别，支持对齐和说话人分离，返回结构化数据并存储到 MinIO"""
    
    try:
        print(f"开始语音识别: {audio_path}")
        
        # 从 MinIO 下载音频文件到临时位置
        storage = get_storage()
        temp_audio_path = storage.download_file(
            task_id=task_id,
            step="extract_audio",
            object_name=os.path.basename(audio_path)
        )
        
        # 检查音频文件是否存在
        if not os.path.exists(temp_audio_path):
            raise FileNotFoundError(f"音频文件不存在: {temp_audio_path}")
        
        # 检查文件大小
        file_size = os.path.getsize(temp_audio_path)
        if file_size == 0:
            raise ValueError("音频文件为空")
        
        print(f"音频文件大小: {file_size} bytes")
        
        # 配置模型参数
        model_size = "large-v3"
        batch_size = int(os.getenv("WHISPER_BATCH_SIZE", "16"))
        
        # 根据环境变量决定运行设备
        device = os.getenv("WHISPER_DEVICE", "cpu")
        compute_type = os.getenv("WHISPER_COMPUTE_TYPE", "int8")
        
        print(f"使用设备: {device}, 计算类型: {compute_type}, 批处理大小: {batch_size}")
        print("使用引擎: WhisperX")
        
        # 使用 WhisperX 进行语音识别
        result = _process_with_whisperx(temp_audio_path, model_size, device, compute_type, batch_size)
        
        # 处理识别结果
        segments_data = []
        for segment in result["segments"]:
            segment_text = segment.get("text", "").strip()
            if segment_text:  # 只添加非空文本
                # 处理word级别的数据
                words_data = []
                if "words" in segment:
                    for word in segment["words"]:
                        word_data = {
                            "start": round(word.get("start", 0), 3),
                            "end": round(word.get("end", 0), 3),
                            "word": word.get("word", "").strip(),
                            "probability": round(word.get("probability", 0), 3) if word.get("probability") is not None else None
                        }
                        words_data.append(word_data)
                
                segment_data = {
                    "start": round(segment.get("start", 0), 3),
                    "end": round(segment.get("end", 0), 3),
                    "text": segment_text,
                    "words": words_data
                }
                segments_data.append(segment_data)
        
        # 构建返回结果
        result_data = {
            "language": result.get("language", "unknown"),
            "segments": segments_data,
            "total_segments": len(segments_data),
            "total_duration": round(segments_data[-1]["end"] if segments_data else 0, 3),
        }

        # 将结果存储到 MinIO
        result_filename = f"speech_result_{uuid.uuid4().hex}.json"
        result_json = json.dumps(result_data, ensure_ascii=False, indent=2)
        
        object_path = storage.upload_data(
            task_id=task_id,
            step="speech_to_text",
            data=result_json.encode('utf-8'),
            object_name=result_filename
        )
        
        # 清理临时文件
        os.unlink(temp_audio_path)
        
        print(f"语音识别结果已存储到 MinIO: {object_path}")
        return result_data
        
    except Exception as e:
        error_msg = f"语音识别失败: {str(e)}"
        print(error_msg)
        raise RuntimeError(error_msg) from e


def _process_with_whisperx(audio_path: str, model_size: str, device: str, compute_type: str, batch_size: int) -> Dict[str, Any]:
    """使用 WhisperX 处理音频"""
    print("正在加载 WhisperX 模型...")
    model = whisperx.load_model(model_size, device, compute_type=compute_type)
    
    # 加载音频
    audio = whisperx.load_audio(audio_path)
    
    # 执行语音识别
    print("正在执行语音识别...")
    result = model.transcribe(audio, batch_size=batch_size)
    print(f"检测到的语言: '{result['language']}'")
    
    # 2. 对齐 Whisper 输出
    print("正在加载对齐模型...")
    model_a, metadata = whisperx.load_align_model(language_code=result["language"], device=device)
    result = whisperx.align(result["segments"], model_a, metadata, audio, device, return_char_alignments=False)

    return result

