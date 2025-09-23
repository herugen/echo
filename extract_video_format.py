"""
音频提取任务
使用 FFmpeg 提取音频，并存储到 MinIO
"""

import os
import uuid
import subprocess
import json
import tempfile
from minio_storage import get_storage


async def extract_video_format(video_path: str, task_id: str) -> str:
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
        width = None
        height = None
        for stream in data.get('streams', []):
            if stream.get('codec_type') == 'video':
                width = stream.get('width', None)
                height = stream.get('height', None)
                
                if width and height:
                    # 清理临时文件
                    try:
                        os.unlink(temp_video_path)
                    except OSError:
                        pass

                    # 创建format信息文件
                    format_info = {
                        "width": width,
                        "height": height
                    }

                    local_format_path = os.path.join(tempfile.gettempdir(), f"video_format_{uuid.uuid4().hex}.json")
                    with open(local_format_path, 'w', encoding='utf-8') as f:
                        json.dump(format_info, f)

                    # 上传到format信息到MinIO
                    object_path = storage.upload_file(
                        task_id=task_id,
                        step="extract_video_format",
                        local_file_path=local_format_path,
                        object_name=f"video_format_{uuid.uuid4().hex}.json"
                    )

                    # 清理临时文件
                    try:
                        os.unlink(local_format_path)
                    except OSError:
                        pass
                    return object_path
    
        # 清理临时文件
        try:
            os.unlink(temp_video_path)
        except OSError:
            pass
    
    return None
