"""
字幕生成任务
使用修正后的segments生成字幕文件，并保存到MinIO
"""

import os
import uuid
import tempfile
import json
from typing import List, Dict, Any
from minio_storage import get_storage


async def gen_translated_subtitle(segments_data: List[Dict[str, Any]], task_id: str, format_path: str) -> str:
    """
    使用翻译后的segments生成字幕文件，并保存到MinIO
    
    Args:
        segments_data: 文本片段数据
        task_id: 任务ID
        format_path: 视频格式信息文件路径
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

        if not format_path:
            print("未找到视频格式信息文件")
            return None

        # 从MinIO下载视频格式信息文件
        format_file_path = storage.download_file_by_path(format_path)
        if not format_file_path:
            print("未找到视频格式信息文件")
            return None

        # 读取并解析JSON文件
        try:
            with open(format_file_path, 'r', encoding='utf-8') as f:
                format_info = json.load(f)
        except (json.JSONDecodeError, FileNotFoundError) as e:
            print(f"读取视频格式信息文件失败: {e}")
            return None
        video_width = format_info["width"]
        video_height = format_info["height"]
        is_vertical = False
        if video_height > video_width:
            is_vertical = True
        
        print(f"视频格式信息: {format_info}，视频方向: {is_vertical}")

        srt_content = generate_srt_from_segments(segments_data)

        # 创建SRT字幕文件
        srt_path = os.path.join(tempfile.gettempdir(), f"subtitle_{task_id}_{uuid.uuid4().hex}.srt")
        with open(srt_path, 'w', encoding='utf-8') as f:
            f.write(srt_content)
        
        # 上传SRT字幕到MinIO
        object_name = f"subtitle_{uuid.uuid4().hex}.srt"
        minio_path = storage.upload_file(
            task_id=task_id,
            step="gen_translated_subtitle",
            local_file_path=srt_path,
            object_name=object_name
        )
        
        # 清理临时文件
        try:
            os.unlink(srt_path)
        except OSError as e:
            print(f"清理临时文件时出错: {e}")
        
        print(f"SRT字幕文件已生成: {minio_path}")
        
        # 返回字幕文件信息
        return minio_path
        
    except (OSError, ValueError, RuntimeError) as e:
        print(f"生成字幕文件失败: {str(e)}")
        return None


def generate_srt_from_segments(segments_data: List[Dict[str, Any]]) -> str:
    """
    从翻译后的segments数据生成SRT字幕内容
    
    Args:
        segments_data: 翻译后的文本片段数据，只使用text字段，忽略words字段
    Returns:
        str: SRT格式的字幕内容
    """
    srt_content = ""
    
    # 翻译后的segments直接使用segment级别，忽略words字段
    for i, segment in enumerate(segments_data, 1):
        if not segment.get("text", "").strip():
            continue
            
        start_time = format_srt_timestamp(segment["start"])
        end_time = format_srt_timestamp(segment["end"])
        text = segment["text"].strip()

        # SRT格式：序号、时间、文本、空行
        srt_content += f"{i}\n"
        srt_content += f"{start_time} --> {end_time}\n"
        srt_content += f"{text}\n\n"
    
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