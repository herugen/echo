"""
音频分割任务
根据字幕时间分割音频，并存储到 MinIO
"""

import os
import uuid
import subprocess
import re
from typing import List, Dict, Any
from minio_storage import get_storage


async def split_audio_by_subtitle(audio_path: str, subtitle_path: str, task_id: str) -> List[str]:
    """根据字幕时间分割音频并存储到 MinIO"""

    print(f"分割音频: {audio_path}")
    
    # 从 MinIO 下载音频文件到临时位置
    storage = get_storage()
    temp_audio_path = storage.download_file(
        task_id=task_id,
        step="extract_audio",
        object_name=os.path.basename(audio_path)
    )
    
    # 从 MinIO 下载字幕文件到临时位置
    temp_subtitle_path = storage.download_file(
        task_id=task_id,
        step="generate_subtitle",
        object_name=os.path.basename(subtitle_path)
    )
    
    # 解析 SRT 字幕文件，提取时间信息
    subtitle_segments = parse_srt_file(temp_subtitle_path)
    print(f"解析到 {len(subtitle_segments)} 个字幕片段")
    
    # 根据时间信息分割音频
    audio_segments = []
    for i, segment in enumerate(subtitle_segments):
        segment_filename = f"audio_segment_{i+1:05d}_{uuid.uuid4().hex[:8]}.wav"
        temp_segment_path = f"/tmp/{segment_filename}"
        
        # 使用 FFmpeg 根据时间戳分割音频
        start_time = segment["start_time"]
        duration = segment["end_time"] - segment["start_time"]
        
        print(f"分割音频片段 {i+1}: {start_time:.3f}s -> {segment['end_time']:.3f}s (时长: {duration:.3f}s)")
        
        cmd = [
            "ffmpeg",
            "-i", temp_audio_path,
            "-ss", str(start_time),
            "-t", str(duration),
            "-c", "copy",  # 使用流复制，避免重新编码
            "-avoid_negative_ts", "make_zero",
            "-y",
            temp_segment_path
        ]
        
        try:
            subprocess.run(cmd, capture_output=True, check=True, text=True)
            
            # 检查生成的音频文件是否存在且大小合理
            if os.path.exists(temp_segment_path) and os.path.getsize(temp_segment_path) > 0:
                # 上传到 MinIO
                object_path = storage.upload_file(
                    task_id=task_id,
                    step="split_audio",
                    local_file_path=temp_segment_path,
                    object_name=segment_filename
                )
                
                audio_segments.append(object_path)
                print(f"音频片段 {i+1} 已上传: {object_path}")
                
                # 清理临时文件
                os.unlink(temp_segment_path)
            else:
                print(f"警告: 音频片段 {i+1} 生成失败或文件为空")
                
        except subprocess.CalledProcessError as e:
            print(f"分割音频片段 {i+1} 失败: {e}")
            print(f"FFmpeg 错误输出: {e.stderr}")
    
    # 清理临时文件
    os.unlink(temp_audio_path)
    os.unlink(temp_subtitle_path)
    
    print(f"音频分割完成，生成了 {len(audio_segments)} 个片段")
    return audio_segments


def parse_srt_file(srt_path: str) -> List[Dict[str, Any]]:
    """解析 SRT 字幕文件，提取时间信息和文本"""
    segments = []
    
    with open(srt_path, 'r', encoding='utf-8') as f:
        content = f.read()
    
    # 使用正则表达式匹配 SRT 格式
    # 匹配模式: 序号\n时间戳\n文本\n\n
    pattern = r'(\d+)\n(\d{2}:\d{2}:\d{2},\d{3})\s*-->\s*(\d{2}:\d{2}:\d{2},\d{3})\n(.*?)(?=\n\d+\n|\n*$)'
    matches = re.findall(pattern, content, re.DOTALL)
    
    for match in matches:
        index, start_time_str, end_time_str, text = match
        
        # 转换时间格式 HH:MM:SS,mmm 为秒数
        start_time = srt_time_to_seconds(start_time_str)
        end_time = srt_time_to_seconds(end_time_str)
        
        # 清理文本（去除多余的空白字符）
        text = text.strip().replace('\n', ' ')
        
        segments.append({
            "index": int(index),
            "start_time": start_time,
            "end_time": end_time,
            "text": text
        })
    
    return segments


def srt_time_to_seconds(time_str: str) -> float:
    """将 SRT 时间格式 (HH:MM:SS,mmm) 转换为秒数"""
    # 解析时间格式: HH:MM:SS,mmm
    time_part, millisec_part = time_str.split(',')
    hours, minutes, seconds = map(int, time_part.split(':'))
    milliseconds = int(millisec_part)
    
    total_seconds = hours * 3600 + minutes * 60 + seconds + milliseconds / 1000.0
    return total_seconds
