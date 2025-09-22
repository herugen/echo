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


def detect_video_orientation(video_files: List[Dict], storage) -> str:
    """
    检测视频方向（竖屏/横屏）
    
    Args:
        video_files: 视频文件列表
        storage: MinIO存储实例
        
    Returns:
        str: 'portrait' 或 'landscape'
    """
    try:
        # 找到第一个视频文件
        video_file = None
        for file_info in video_files:
            if file_info["object_name"].endswith(('.mp4', '.mkv', '.avi', '.mov')):
                video_file = file_info["object_name"]
                break
        
        if not video_file:
            return 'landscape'  # 默认横屏
        
        # 下载视频文件到临时位置
        temp_video_path = storage.download_file_by_path(video_file)
        
        # 使用ffprobe检测视频尺寸
        cmd = [
            'ffprobe', '-v', 'quiet', '-print_format', 'json', '-show_streams',
            temp_video_path
        ]
        
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=30, check=False)
        
        if result.returncode == 0:
            data = json.loads(result.stdout)
            
            for stream in data.get('streams', []):
                if stream.get('codec_type') == 'video':
                    width = stream.get('width', 0)
                    height = stream.get('height', 0)
                    
                    if width > 0 and height > 0:
                        # 清理临时文件
                        try:
                            os.unlink(temp_video_path)
                        except OSError:
                            pass
                        
                        # 判断方向：高度大于宽度为竖屏
                        return 'portrait' if height > width else 'landscape'
        
        # 清理临时文件
        try:
            os.unlink(temp_video_path)
        except OSError:
            pass
            
    except (OSError, subprocess.TimeoutExpired, json.JSONDecodeError, ValueError) as e:
        print(f"检测视频方向时出错: {e}")
    
    return 'landscape'  # 默认横屏


async def add_subtitle_to_video(subtitle_info: Dict[str, str], task_id: str) -> str:
    """
    给视频加上原生字幕，生成中间产物视频文件并保存到MinIO
    
    Args:
        subtitle_info: 字幕文件信息字典，包含landscape和portrait路径
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
        
        # 检测视频方向
        video_orientation = detect_video_orientation(video_files, storage)
        print(f"检测到视频方向: {'竖屏' if video_orientation == 'portrait' else '横屏'}")
        
        # 根据视频方向选择对应的字幕文件
        if video_orientation == 'portrait':
            subtitle_path = subtitle_info.get('portrait')
            print("使用竖屏字幕文件")
        else:
            subtitle_path = subtitle_info.get('landscape')
            print("使用横屏字幕文件")
        
        if not subtitle_path:
            print(f"未找到{video_orientation}字幕文件")
            return None
        
        # 下载原始视频到本地临时文件
        temp_video_path = storage.download_file_by_path(video_file)
        
        # 从MinIO下载字幕文件
        temp_subtitle_path = storage.download_file_by_path(subtitle_path)

        # 生成带字幕的视频文件
        output_video_path = await generate_subtitled_video(temp_video_path, temp_subtitle_path, task_id)
        
        # 上传到MinIO
        object_name = f"subtitled_video_{uuid.uuid4().hex}.mp4"
        minio_path = storage.upload_file(
            task_id=task_id,
            step="add_subtitle",
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
        
        print(f"带字幕的中间视频已生成并保存到MinIO: {minio_path}")
        return minio_path
        
    except (OSError, ValueError, RuntimeError) as e:
        print(f"生成带字幕视频失败: {str(e)}")
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
        output_path = os.path.join(tempfile.gettempdir(), f"subtitled_{task_id}_{uuid.uuid4().hex}.mp4")
        
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
        
        print(f"带字幕视频生成成功: {output_path}")
        return output_path
        
    except (OSError, ValueError, RuntimeError) as e:
        print(f"生成带字幕视频时出错: {str(e)}")
        raise