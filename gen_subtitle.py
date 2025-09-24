"""
字幕生成任务
使用修正后的segments生成SRT字幕文件，并保存到MinIO
"""

import os
import uuid
import tempfile
from typing import List, Dict, Any
from minio_storage import get_storage


async def gen_subtitle(segments_data: List[Dict[str, Any]], task_id: str) -> str:
    """
    使用修正后的segments生成SRT字幕文件，并保存到MinIO
    
    Args:
        segments_data: 文本片段数据
        task_id: 任务ID
        
    Returns:
        str: 字幕文件在MinIO中的路径
    """
    try:
        print(f"开始生成字幕文件，共 {len(segments_data)} 个片段")
        
        if not segments_data:
            print("没有文本片段，跳过字幕文件生成")
            return None
        
        # 获取存储实例
        storage = get_storage()
        
        # 生成SRT字幕文件
        print("生成SRT字幕文件...")
        subtitle_content = generate_srt_from_segments(segments_data)
        
        # 创建SRT字幕文件
        subtitle_path = os.path.join(tempfile.gettempdir(), f"subtitle_{task_id}_{uuid.uuid4().hex}.srt")
        with open(subtitle_path, 'w', encoding='utf-8') as f:
            f.write(subtitle_content)
        
        # 上传SRT字幕到MinIO
        subtitle_object_name = f"subtitle_{uuid.uuid4().hex}.srt"
        subtitle_minio_path = storage.upload_file(
            task_id=task_id,
            step="gen_subtitle",
            local_file_path=subtitle_path,
            object_name=subtitle_object_name
        )
        
        # 清理临时文件
        try:
            os.unlink(subtitle_path)
        except OSError as e:
            print(f"清理临时文件时出错: {e}")
        
        print(f"SRT字幕文件已生成: {subtitle_minio_path}")
        
        # 返回字幕文件信息
        return subtitle_minio_path
        
    except (OSError, ValueError, RuntimeError) as e:
        print(f"生成字幕文件失败: {str(e)}")
        return None


def generate_srt_from_segments(segments_data: List[Dict[str, Any]]) -> str:
    """
    从segments数据生成SRT字幕内容
    
    Args:
        segments_data: 文本片段数据
    Returns:
        str: SRT格式的字幕内容
    """
    srt_content = ""
    subtitle_index = 1
    
    for segment in segments_data:
        if not segment.get("text", "").strip():
            continue
            
        # 格式化时间戳为SRT格式 (HH:MM:SS,mmm)
        start_time = format_srt_timestamp(segment["start"])
        end_time = format_srt_timestamp(segment["end"])
        text = segment["text"].strip()
        
        # 构建SRT字幕条目
        srt_content += f"{subtitle_index}\n"
        srt_content += f"{start_time} --> {end_time}\n"
        srt_content += f"{text}\n\n"
        
        subtitle_index += 1
    
    return srt_content


def format_srt_timestamp(seconds: float) -> str:
    """
    将秒数转换为SRT时间戳格式 (HH:MM:SS,mmm)
    
    Args:
        seconds: 秒数
        
    Returns:
        str: 格式化的时间戳
    """
    hours = int(seconds // 3600)
    minutes = int((seconds % 3600) // 60)
    secs = int(seconds % 60)
    milliseconds = int((seconds % 1) * 1000)
    
    return f"{hours:02d}:{minutes:02d}:{secs:02d},{milliseconds:03d}"
