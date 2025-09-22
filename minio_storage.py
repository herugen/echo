"""
MinIO 对象存储服务
用于存储视频翻译工作流中的中间产物
"""

import os
import uuid
from typing import Optional
from minio import Minio
from minio.error import S3Error
import tempfile
import logging

# 配置日志
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class MinIOStorage:
    """MinIO 存储服务类"""
    
    def __init__(self):
        """初始化 MinIO 客户端"""
        # 从环境变量获取配置
        self.endpoint = os.getenv("MINIO_ENDPOINT")
        self.access_key = os.getenv("MINIO_ACCESS_KEY")
        self.secret_key = os.getenv("MINIO_SECRET_KEY")
        self.bucket_name = os.getenv("MINIO_BUCKET", "video-translation")
        self.secure = os.getenv("MINIO_SECURE", "true").lower() == "true"
        
        # 验证必要的配置
        if not all([self.endpoint, self.access_key, self.secret_key]):
            raise ValueError("MinIO 配置不完整，请检查环境变量")
        
        # 创建 MinIO 客户端
        self.client = Minio(
            endpoint=self.endpoint,
            access_key=self.access_key,
            secret_key=self.secret_key,
            secure=self.secure
        )
        
        # 确保存储桶存在
        self._ensure_bucket_exists()
    
    def _ensure_bucket_exists(self):
        """确保存储桶存在"""
        try:
            if not self.client.bucket_exists(self.bucket_name):
                self.client.make_bucket(self.bucket_name)
                logger.info("创建存储桶: %s", self.bucket_name)
        except S3Error as e:
            logger.error("创建存储桶失败: %s", e)
            raise
    
    def _get_object_path(self, task_id: str, step: str, filename: str) -> str:
        """生成对象存储路径"""
        return f"{task_id}/{step}/{filename}"
    
    def upload_file(self, task_id: str, step: str, local_file_path: str, 
                   object_name: Optional[str] = None) -> str:
        """
        上传文件到 MinIO
        
        Args:
            task_id: 任务ID
            step: 处理步骤名称
            local_file_path: 本地文件路径
            object_name: 对象名称，如果为None则使用原文件名
            
        Returns:
            str: 对象存储路径
        """
        try:
            # 生成对象名称
            if object_name is None:
                object_name = os.path.basename(local_file_path)
            
            # 生成完整路径
            object_path = self._get_object_path(task_id, step, object_name)
            
            # 上传文件
            self.client.fput_object(
                bucket_name=self.bucket_name,
                object_name=object_path,
                file_path=local_file_path
            )
            
            logger.info("文件上传成功: %s", object_path)
            return object_path
            
        except S3Error as e:
            logger.error("文件上传失败: %s", e)
            raise
        except Exception as e:
            logger.error("文件上传异常: %s", e)
            raise
    
    def download_file_by_path(self, object_path: str, 
                              local_file_path: Optional[str] = None) -> str:
        """
        通过完整对象路径下载文件
        
        Args:
            object_path: 完整的对象路径
            local_file_path: 本地保存路径，如果为None则使用临时文件
            
        Returns:
            str: 本地文件路径
        """
        try:
            # 生成本地文件路径
            if local_file_path is None:
                # 创建临时文件
                temp_dir = tempfile.gettempdir()
                filename = os.path.basename(object_path)
                local_file_path = os.path.join(temp_dir, f"temp_{uuid.uuid4().hex}_{filename}")
            
            # 确保目录存在
            os.makedirs(os.path.dirname(local_file_path), exist_ok=True)
            
            # 下载文件
            self.client.fget_object(
                bucket_name=self.bucket_name,
                object_name=object_path,
                file_path=local_file_path
            )
            
            logger.info("文件下载成功: %s -> %s", object_path, local_file_path)
            return local_file_path
            
        except S3Error as e:
            logger.error("文件下载失败: %s", e)
            raise
        except Exception as e:
            logger.error("文件下载异常: %s", e)
            raise

    def download_file(self, task_id: str, step: str, object_name: str, 
                     local_file_path: Optional[str] = None) -> str:
        """
        从 MinIO 下载文件
        
        Args:
            task_id: 任务ID
            step: 处理步骤名称
            object_name: 对象名称
            local_file_path: 本地保存路径，如果为None则使用临时文件
            
        Returns:
            str: 本地文件路径
        """
        try:
            # 生成对象路径
            object_path = self._get_object_path(task_id, step, object_name)
            
            # 生成本地文件路径
            if local_file_path is None:
                # 创建临时文件
                temp_dir = tempfile.gettempdir()
                local_file_path = os.path.join(temp_dir, f"temp_{uuid.uuid4().hex}_{object_name}")
            
            # 确保目录存在
            os.makedirs(os.path.dirname(local_file_path), exist_ok=True)
            
            # 下载文件
            self.client.fget_object(
                bucket_name=self.bucket_name,
                object_name=object_path,
                file_path=local_file_path
            )
            
            logger.info("文件下载成功: %s -> %s", object_path, local_file_path)
            return local_file_path
            
        except S3Error as e:
            logger.error("文件下载失败: %s", e)
            raise
        except Exception as e:
            logger.error("文件下载异常: %s", e)
            raise
    
    def upload_data(self, task_id: str, step: str, data: bytes, 
                   object_name: str) -> str:
        """
        上传字节数据到 MinIO
        
        Args:
            task_id: 任务ID
            step: 处理步骤名称
            data: 字节数据
            object_name: 对象名称
            
        Returns:
            str: 对象存储路径
        """
        try:
            # 生成对象路径
            object_path = self._get_object_path(task_id, step, object_name)
            
            # 创建临时文件
            with tempfile.NamedTemporaryFile(delete=False) as temp_file:
                temp_file.write(data)
                temp_file_path = temp_file.name
            
            # 上传文件
            self.client.fput_object(
                bucket_name=self.bucket_name,
                object_name=object_path,
                file_path=temp_file_path
            )
            
            # 清理临时文件
            os.unlink(temp_file_path)
            
            logger.info("数据上传成功: %s", object_path)
            return object_path
            
        except Exception as e:
            logger.error("数据上传异常: %s", e)
            raise
    
    def download_data(self, task_id: str, step: str, object_name: str) -> bytes:
        """
        从 MinIO 下载字节数据
        
        Args:
            task_id: 任务ID
            step: 处理步骤名称
            object_name: 对象名称
            
        Returns:
            bytes: 文件数据
        """
        try:
            # 生成对象路径
            object_path = self._get_object_path(task_id, step, object_name)
            
            # 下载数据
            response = self.client.get_object(
                bucket_name=self.bucket_name,
                object_name=object_path
            )
            
            data = response.read()
            response.close()
            response.release_conn()
            
            logger.info("数据下载成功: %s", object_path)
            return data
            
        except S3Error as e:
            logger.error("数据下载失败: %s", e)
            raise
        except Exception as e:
            logger.error("数据下载异常: %s", e)
            raise
    
    def delete_file(self, task_id: str, step: str, object_name: str) -> bool:
        """
        删除 MinIO 中的文件
        
        Args:
            task_id: 任务ID
            step: 处理步骤名称
            object_name: 对象名称
            
        Returns:
            bool: 删除是否成功
        """
        try:
            # 生成对象路径
            object_path = self._get_object_path(task_id, step, object_name)
            
            # 删除文件
            self.client.remove_object(
                bucket_name=self.bucket_name,
                object_name=object_path
            )
            
            logger.info("文件删除成功: %s", object_path)
            return True
            
        except S3Error as e:
            logger.error("文件删除失败: %s", e)
            return False
        except Exception as e:
            logger.error("文件删除异常: %s", e)
            return False
    
    def list_files(self, task_id: str, step: Optional[str] = None) -> list:
        """
        列出指定任务的文件
        
        Args:
            task_id: 任务ID
            step: 处理步骤名称，如果为None则列出所有步骤
            
        Returns:
            list: 文件列表
        """
        try:
            prefix = f"{task_id}/"
            if step:
                prefix += f"{step}/"
            
            objects = self.client.list_objects(
                bucket_name=self.bucket_name,
                prefix=prefix,
                recursive=True
            )
            
            files = []
            for obj in objects:
                files.append({
                    "object_name": obj.object_name,
                    "size": obj.size,
                    "last_modified": obj.last_modified
                })
            
            return files
            
        except S3Error as e:
            logger.error("列出文件失败: %s", e)
            return []
        except Exception as e:
            logger.error("列出文件异常: %s", e)
            return []
    
    def get_file_url(self, task_id: str, step: str, object_name: str, 
                    expires_in_seconds: int = 3600) -> str:
        """
        获取文件的预签名URL
        
        Args:
            task_id: 任务ID
            step: 处理步骤名称
            object_name: 对象名称
            expires_in_seconds: URL过期时间（秒）
            
        Returns:
            str: 预签名URL
        """
        try:
            # 生成对象路径
            object_path = self._get_object_path(task_id, step, object_name)
            
            # 生成预签名URL
            url = self.client.presigned_get_object(
                bucket_name=self.bucket_name,
                object_name=object_path,
                expires=expires_in_seconds
            )
            
            return url
            
        except S3Error as e:
            logger.error("生成预签名URL失败: %s", e)
            raise
        except Exception as e:
            logger.error("生成预签名URL异常: %s", e)
            raise


# 全局存储实例
_storage_instance = None


def get_storage() -> MinIOStorage:
    """获取全局存储实例"""
    global _storage_instance
    if _storage_instance is None:
        _storage_instance = MinIOStorage()
    return _storage_instance
