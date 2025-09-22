"""
音频提取任务
使用 FFmpeg 提取音频，并存储到 MinIO
"""

import os
import uuid
import subprocess
from minio_storage import get_storage


async def extract_audio(video_path: str, task_id: str) -> str:
    """使用 FFmpeg 提取音频并存储到 MinIO"""
    
    # 从 MinIO 下载视频文件到临时位置
    storage = get_storage()
    temp_video_path = storage.download_file(
        task_id=task_id,
        step="download",
        object_name=os.path.basename(video_path)
    )
    
    # 生成音频文件名
    audio_filename = f"audio_{uuid.uuid4().hex}.wav"
    temp_audio_path = f"/tmp/{audio_filename}"
    
    # 确保目录存在
    os.makedirs("/tmp", exist_ok=True)
    
    try:
        print(f"正在提取音频: {temp_video_path} -> {temp_audio_path}")
        
        # 使用 FFmpeg 提取音频
        cmd = [
            "ffmpeg",
            "-i", temp_video_path,
            "-vn",  # 禁用视频
            "-acodec", "pcm_s16le",  # 音频编码器
            "-ar", "44100",  # 采样率
            "-ac", "2",  # 声道数
            "-y",  # 覆盖输出文件
            temp_audio_path
        ]
        
        # 执行 FFmpeg 命令
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=300  # 5分钟超时
        )
        
        if result.returncode == 0:
            print(f"音频提取成功: {temp_audio_path}")
            
            # 检查文件是否存在且大小大于0
            if os.path.exists(temp_audio_path) and os.path.getsize(temp_audio_path) > 0:
                # 上传到 MinIO
                object_path = storage.upload_file(
                    task_id=task_id,
                    step="extract_audio",
                    local_file_path=temp_audio_path,
                    object_name=audio_filename
                )
                
                # 清理临时文件
                os.unlink(temp_audio_path)
                os.unlink(temp_video_path)
                
                print(f"音频已上传到 MinIO: {object_path}")
                return object_path
            else:
                raise Exception("提取的音频文件为空或不存在")
        else:
            error_msg = result.stderr if result.stderr else "未知错误"
            raise Exception(f"FFmpeg 提取音频失败: {error_msg}")
            
    except subprocess.TimeoutExpired:
        raise Exception("音频提取超时，请检查视频文件是否过大")
    except FileNotFoundError:
        raise Exception("FFmpeg 未安装或不在 PATH 中")
    except Exception as e:
        raise Exception(f"提取音频失败: {str(e)}")
