"""
音频提取任务
使用 FFmpeg 提取音频，并存储到 MinIO
"""

import os
import uuid
import subprocess
import json
from minio_storage import get_storage


async def extract_video_format(video_path: str, task_id: str) -> tuple[int, int]:
    """使用 FFmpeg 提取音频并存储到 MinIO"""
    
    # 从 MinIO 下载视频文件到临时位置
    storage = get_storage()
    temp_video_path = storage.download_file(
        task_id=task_id,
        step="download",
        object_name=os.path.basename(video_path)
    )
    
    # 使用ffprobe检测视频尺寸
    cmd = [
        'ffprobe', '-v', 'quiet', '-print_format', 'json', '-show_streams',
        temp_video_path
    ]
    
    result = subprocess.run(cmd, capture_output=True, text=True, timeout=30, check=False)
    
    if result.returncode == 0:
        data = json.loads(result.stdout)
        width = -1
        height = -1
        for stream in data.get('streams', []):
            if stream.get('codec_type') == 'video':
                width = stream.get('width', -1)
                height = stream.get('height', -1)
                
                if width > 0 and height > 0:
                    # 清理临时文件
                    try:
                        os.unlink(temp_video_path)
                    except OSError:
                        pass
                    
                    # 判断方向：高度大于宽度为竖屏
                    return width, height
    
        # 清理临时文件
        try:
            os.unlink(temp_video_path)
        except OSError:
            pass
    
    return -1, -1
