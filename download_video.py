"""
视频下载任务
使用 Cobalt 下载视频，并存储到 MinIO
"""

import os
import requests
import uuid
from minio_storage import get_storage


async def download_video(url: str, task_id: str) -> str:
    """使用 Cobalt 下载视频并存储到 MinIO"""
    
    # Cobalt 服务配置
    cobalt_service_url = os.getenv("COBALT_SERVICE_URL", "http://localhost:9000")
    
    # 请求参数
    payload = {
        "url": url,
    }
    
    headers = {
        "Accept": "application/json",
        "Content-Type": "application/json"
    }
    
    try:
        # 调用 Cobalt API
        print(f"正在调用 Cobalt 服务下载视频: {url}")
        response = requests.post(
            cobalt_service_url, 
            json=payload, 
            headers=headers,
            timeout=30
        )
        
        if response.status_code == 200:
            result = response.json()
            
            if result.get("status") in ["tunnel", "redirect"]:
                # 获取下载链接
                download_url = result.get("url")
                if not download_url:
                    raise Exception("Cobalt 返回的下载链接为空")
                
                print(f"获取到下载链接: {download_url}")
                
                # 下载文件到临时位置
                video_filename = f"video_{uuid.uuid4().hex}.mp4"
                temp_dir = "/tmp"
                temp_video_path = os.path.join(temp_dir, video_filename)
                
                # 确保目录存在
                os.makedirs(temp_dir, exist_ok=True)
                
                # 下载视频文件
                print(f"正在下载视频到: {temp_video_path}")
                video_response = requests.get(download_url, stream=True, timeout=60)
                video_response.raise_for_status()
                
                with open(temp_video_path, "wb") as f:
                    for chunk in video_response.iter_content(chunk_size=8192):
                        f.write(chunk)
                
                print(f"视频下载完成: {temp_video_path}")
                
                # 上传到 MinIO
                storage = get_storage()
                object_path = storage.upload_file(
                    task_id=task_id,
                    step="download",
                    local_file_path=temp_video_path,
                    object_name=video_filename
                )
                
                # 清理临时文件
                os.unlink(temp_video_path)
                
                print(f"视频已上传到 MinIO: {object_path}")
                return object_path
                
            elif result.get("status") == "picker":
                # 需要用户选择媒体项
                raise Exception("需要用户选择具体的媒体项，请检查视频链接")
                
            else:
                # 处理错误
                error_msg = result.get("error", "未知错误")
                raise Exception(f"Cobalt 处理失败: {error_msg}")
                
        else:
            raise Exception(f"Cobalt API 请求失败，状态码: {response.status_code}")
            
    except requests.exceptions.Timeout:
        raise Exception("Cobalt 服务请求超时")
    except requests.exceptions.ConnectionError:
        raise Exception("无法连接到 Cobalt 服务，请检查服务是否启动")
    except Exception as e:
        raise Exception(f"下载视频失败: {str(e)}")
