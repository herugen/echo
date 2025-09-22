"""
给视频加上原生字幕
使用修正后的segments生成带字幕的中间视频文件，并保存到MinIO
"""

import os
import uuid
import tempfile
import asyncio
import subprocess
import json
from typing import List, Dict
from minio_storage import get_storage

async def add_translated_subtitle_to_video(subtitle_path: str, task_id: str) -> str:
    """
    给视频加上原生字幕，生成中间产物视频文件并保存到MinIO
    
    Args:
        subtitle_path: 字幕文件MinIO路径
        task_id: 任务ID
        
    Returns:
        str: 中间视频文件在MinIO中的路径
    """
    try:
        print("开始生成带字幕的中间视频")
        
        # 获取存储实例
        storage = get_storage()
        
        # 从MinIO下载原始视频文件
        # 原始视频文件存储在download步骤中
        video_files = storage.list_files(task_id, "download")
        if not video_files:
            print("未找到原始视频文件")
            return None
        
        # 找到视频文件（假设是.mp4或.mkv格式）
        video_file = None
        for file_info in video_files:
            if file_info["object_name"].endswith(('.mp4', '.mkv', '.avi', '.mov')):
                video_file = file_info["object_name"]
                break
        
        if not video_file:
            print("未找到支持的视频文件格式")
            return None
        
        # 下载原始视频到本地临时文件
        temp_video_path = storage.download_file_by_path(video_file)

        # 从MinIO下载字幕文件
        temp_subtitle_path = storage.download_file_by_path(subtitle_path)

        # 生成带字幕的视频文件
        output_video_path = await generate_subtitled_video(temp_video_path, temp_subtitle_path, task_id)
        
        # 上传到MinIO
        object_name = f"translated_subtitled_video_{uuid.uuid4().hex}.mp4"
        minio_path = storage.upload_file(
            task_id=task_id,
            step="add_translated_subtitle",
            local_file_path=output_video_path,
            object_name=object_name
        )
        
        # 清理临时文件
        try:
            os.unlink(temp_video_path)
            os.unlink(temp_subtitle_path)
            os.unlink(output_video_path)
        except OSError as e:
            print(f"清理临时文件时出错: {e}")
        
        print(f"带翻译字幕的中间视频已生成并保存到MinIO: {minio_path}")
        return minio_path
        
    except (OSError, ValueError, RuntimeError) as e:
        print(f"生成带翻译字幕视频失败: {str(e)}")
        return None


async def generate_subtitled_video(input_video_path: str, ass_path: str, task_id: str) -> str:
    """
    使用FFmpeg生成带字幕的视频文件
    
    Args:
        input_video_path: 输入视频文件路径
        ass_path: ASS字幕文件路径
        task_id: 任务ID
        
    Returns:
        str: 输出视频文件路径
    """
    try:
        # 创建输出文件路径
        output_path = os.path.join(tempfile.gettempdir(), f"translated_subtitled_{task_id}_{uuid.uuid4().hex}.mp4")
        
        # 构建FFmpeg命令
        # 使用subtitles滤镜添加ASS字幕，支持word级别高亮
        subtitle_filter = f"subtitles={ass_path}"
        
        cmd = [
            "ffmpeg",
            "-i", input_video_path,
            "-vf", subtitle_filter,
            "-c:a", "copy",  # 保持原音频不变
            "-c:v", "libx264",  # 使用H.264编码
            "-preset", "fast",  # 快速编码
            "-crf", "23",  # 质量设置
            "-y",  # 覆盖输出文件
            output_path
        ]
        
        print(f"执行FFmpeg命令: {' '.join(cmd)}")
        
        # 执行FFmpeg命令
        process = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE
        )
        
        _, stderr = await process.communicate()
        
        if process.returncode != 0:
            print(f"FFmpeg执行失败，返回码: {process.returncode}")
            print(f"错误输出: {stderr.decode()}")
            raise RuntimeError(f"FFmpeg执行失败: {stderr.decode()}")
        
        print(f"带翻译字幕视频生成成功: {output_path}")
        return output_path
        
    except (OSError, ValueError, RuntimeError) as e:
        print(f"生成带翻译字幕视频时出错: {str(e)}")
        raise