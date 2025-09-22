"""
音频替换任务
根据TTS生成的音频和字幕时间信息，精确替换视频中的音频轨道
"""

import os
import uuid
import subprocess
import re
from typing import List, Dict, Any
from minio_storage import get_storage


async def replace_audio_tracks(video_path: str, _original_audio_segments: List[str], tts_audio_segments: List[str], task_id: str, background_volume: float = 0.15) -> str:
    """根据TTS音频替换视频中的音频轨道
    
    Args:
        video_path: 视频文件路径
        _original_audio_segments: 原始音频片段（保留用于API兼容性）
        tts_audio_segments: TTS音频片段列表
        task_id: 任务ID
        background_volume: 背景音频音量比例（保留用于API兼容性）
    """
    print(f"开始音频替换任务，TTS音频片段数量: {len(tts_audio_segments)}")
    
    # 注意: _original_audio_segments 和 background_volume 参数保留用于API兼容性
    
    # 获取存储实例
    storage = get_storage()
    
    # 从 MinIO 下载视频文件到临时位置
    temp_video_path = storage.download_file(
        task_id=task_id,
        step="download",
        object_name=os.path.basename(video_path)
    )
    if not temp_video_path or not os.path.exists(temp_video_path):
        raise ValueError("无法找到视频文件")
    

    
    # 下载所有TTS音频片段到临时目录
    temp_tts_files = []
    for tts_segment_path in tts_audio_segments:
        temp_tts_path = storage.download_file(
            task_id=task_id,
            step="generate_tts",
            object_name=os.path.basename(tts_segment_path)
        )
        temp_tts_files.append(temp_tts_path)
    
    # 对TTS音频文件进行排序，确保与字幕片段顺序一致
    temp_tts_files = sort_tts_files_by_index(temp_tts_files)
    print("TTS音频文件已按索引顺序排序")
    try:
        # 创建混合音频文件
        mixed_audio_path = await create_mixed_audio(
            temp_tts_files, 
            background_volume
        )
        
        # 将混合后的音频替换到视频中
        final_video_path = await replace_video_audio(temp_video_path, mixed_audio_path)
        
        # 上传最终视频到 MinIO
        final_video_filename = f"final_video_{uuid.uuid4().hex}.mp4"
        object_path = storage.upload_file(
            task_id=task_id,
            step="replace_audio",
            local_file_path=final_video_path,
            object_name=final_video_filename
        )
        
        print(f"音频替换完成，最终视频已存储: {final_video_path} {object_path}")
        return object_path
        
    finally:
        # 清理所有临时文件
        temp_files_to_clean = [temp_video_path] + temp_tts_files
        cleanup_temp_files(temp_files_to_clean)






async def create_mixed_audio(tts_files: List[str], background_volume: float = 0.15) -> str:
    """创建混合音频文件，直接拼接TTS音频文件
    
    Args:
        tts_files: TTS音频文件列表
        background_volume: 背景音频音量比例（保留用于API兼容性）
    """
    print("开始创建混合音频")
    
    # 注意：background_volume 参数保留用于API兼容性
    _ = background_volume    # 抑制未使用参数警告
    
    # 创建音频混合脚本
    mixed_audio_path = f"/tmp/mixed_audio_{uuid.uuid4().hex}.wav"
    
    # 使用新的音频拼接方法：直接拼接TTS音频
    try:
        await create_audio_by_subtitle_timing(tts_files, mixed_audio_path)
        print(f"音频拼接完成 {mixed_audio_path}")
        return mixed_audio_path
        
    except Exception as e:
        print(f"音频拼接失败: {e}")
        raise RuntimeError(f"音频拼接失败: {e}") from e


async def create_audio_by_subtitle_timing(tts_files: List[str], output_path: str):
    """直接拼接TTS音频文件，不使用静音填充
    
    Args:
        tts_files: TTS音频文件列表
        output_path: 输出音频文件路径
    """
    print("开始直接拼接TTS音频文件")
    
    # 检测第一个TTS音频文件的格式，作为标准格式
    if not tts_files:
        raise ValueError("没有TTS音频文件")
    
    reference_format = await probe_audio_format(tts_files[0])
    print(f"使用参考音频格式: 采样率={reference_format['sample_rate']}Hz, 声道数={reference_format['channels']}, 编码={reference_format['codec']}")
    
    # 创建音频拼接脚本
    concat_list_path = f"/tmp/concat_list_{uuid.uuid4().hex}.txt"
    temp_files = []
    
    try:
        # 生成拼接列表，直接拼接TTS音频
        await generate_audio_concat_list(tts_files, concat_list_path, temp_files, reference_format)
        
        # 验证拼接列表
        await validate_audio_concat_list(concat_list_path, temp_files)
        
        # 打印拼接列表内容用于调试
        print("拼接列表内容:")
        with open(concat_list_path, 'r', encoding='utf-8') as f:
            for i, line in enumerate(f.readlines()[:10]):  # 只显示前10行
                print(f"  {i+1}: {line.strip()}")
        if len(tts_files) > 10:
            print(f"  ... (还有 {len(tts_files) - 10} 个文件)")

        # 使用ffmpeg拼接音频，使用检测到的格式参数
        cmd = [
            "ffmpeg",
            "-f", "concat",
            "-safe", "0",
            "-i", concat_list_path,
            "-c:a", reference_format["codec"],  # 使用检测到的编码格式
            "-ar", str(reference_format["sample_rate"]),  # 使用检测到的采样率
            "-ac", str(reference_format["channels"]),     # 使用检测到的声道数
            "-y",
            output_path
        ]
        
        print("开始拼接音频...")
        print(f"FFmpeg命令: {' '.join(cmd)}")
        
        try:
            result = subprocess.run(cmd, capture_output=True, check=True, text=True)
            print("FFmpeg拼接成功")
            if result.stderr:
                print(f"FFmpeg输出: {result.stderr}")
        except subprocess.CalledProcessError as e:
            print(f"FFmpeg拼接失败: {e}")
            print(f"错误输出: {e.stderr}")
            raise
        
        # 验证输出音频时长
        audio_duration = await probe_audio_duration(output_path)
        print(f"音频拼接完成，总时长: {audio_duration:.3f}秒")
        
    except Exception as e:
        print(f"音频拼接失败: {e}")
        raise
    finally:
        # 清理临时文件
        cleanup_temp_files([concat_list_path] + temp_files)


async def generate_audio_concat_list(tts_files: List[str], concat_list_path: str, temp_files: List[str], audio_format: Dict[str, Any]):
    """生成音频拼接列表，直接按顺序拼接TTS音频文件
    
    Args:
        tts_files: TTS音频文件列表
        concat_list_path: 拼接列表文件路径
        temp_files: 临时文件列表（用于清理）
        audio_format: 音频格式参数（采样率、声道数、编码格式）
    """
    print("生成音频拼接列表（直接拼接TTS音频）...")
    
    # 抑制未使用参数警告
    _ = audio_format
    _ = temp_files
    
    with open(concat_list_path, 'w', encoding='utf-8') as f:
        for i, tts_file in enumerate(tts_files):
            print(f"添加TTS音频文件 {i+1}/{len(tts_files)}: {os.path.basename(tts_file)}")
            f.write(f"file '{tts_file}'\n")

    print(f"拼接列表已生成: {concat_list_path}")
    print(f"TTS音频文件数量: {len(tts_files)}")




async def validate_audio_concat_list(concat_list_path: str, temp_files: List[str]):  # noqa: ARG001
    """验证音频拼接列表"""
    _ = temp_files  # 抑制未使用参数警告
    print("验证音频拼接列表...")
    with open(concat_list_path, 'r', encoding='utf-8') as f:
        lines = f.readlines()
    print(f"拼接列表已验证: {concat_list_path}")

    total_duration = 0.0
    # 验证所有TTS音频文件
    for line in lines:
        file_path = line.strip().replace("file '", "").replace("'", "")
        if os.path.exists(file_path):
            duration = await probe_audio_duration(file_path)
            total_duration += duration
            print(f"TTS音频文件时长: {duration:.3f}s - {os.path.basename(file_path)}")
        else:
            print(f"警告: TTS音频文件不存在: {file_path}")
    
    print(f"拼接列表总时长: {total_duration:.3f}s")


async def probe_audio_duration(audio_path: str) -> float:
    """获取音频文件时长
    
    Args:
        audio_path: 音频文件路径
    """
    cmd = [
        "ffprobe",
        "-v", "quiet",
        "-show_entries", "format=duration",
        "-of", "csv=p=0",
        audio_path
    ]
    
    result = subprocess.run(cmd, capture_output=True, text=True, check=True)
    actual_duration = float(result.stdout.strip())
    
    return actual_duration


async def probe_audio_format(audio_path: str) -> Dict[str, Any]:
    """检测音频文件的格式信息（采样率、声道数、编码格式）
    
    Args:
        audio_path: 音频文件路径
        
    Returns:
        包含音频格式信息的字典
    """
    try:
        # 分别获取不同的音频属性
        sample_rate = 44100
        channels = 2
        codec = "pcm_s16le"
        
        # 获取采样率
        cmd_rate = [
            "ffprobe",
            "-v", "quiet",
            "-show_entries", "stream=sample_rate",
            "-of", "csv=p=0",
            audio_path
        ]
        result = subprocess.run(cmd_rate, capture_output=True, text=True, check=True)
        if result.stdout.strip():
            sample_rate = int(result.stdout.strip())
        
        # 获取声道数
        cmd_channels = [
            "ffprobe",
            "-v", "quiet",
            "-show_entries", "stream=channels",
            "-of", "csv=p=0",
            audio_path
        ]
        result = subprocess.run(cmd_channels, capture_output=True, text=True, check=True)
        if result.stdout.strip():
            channels = int(result.stdout.strip())
        
        # 获取编码格式
        cmd_codec = [
            "ffprobe",
            "-v", "quiet",
            "-show_entries", "stream=codec_name",
            "-of", "csv=p=0",
            audio_path
        ]
        result = subprocess.run(cmd_codec, capture_output=True, text=True, check=True)
        if result.stdout.strip():
            codec = result.stdout.strip()
        
        print(f"检测到音频格式: 采样率={sample_rate}Hz, 声道数={channels}, 编码={codec}")
        
        return {
            "sample_rate": sample_rate,
            "channels": channels,
            "codec": codec
        }
        
    except (subprocess.CalledProcessError, ValueError, IndexError) as e:
        print(f"音频格式检测失败: {e}，使用默认值")
        return {
            "sample_rate": 44100,
            "channels": 2,
            "codec": "pcm_s16le"
        }


async def replace_video_audio(video_path: str, audio_path: str) -> str:
    """将混合后的音频替换到视频中"""
    print("开始替换视频音频")
    
    final_video_path = f"/tmp/final_video_{uuid.uuid4().hex}.mp4"
    
    cmd = [
        "ffmpeg",
        "-i", video_path,  # 视频输入
        "-i", audio_path,   # 音频输入
        "-c:v", "copy",     # 视频流复制，不重新编码
        "-c:a", "aac",      # 音频编码为AAC
        "-map", "0:v:0",    # 使用第一个输入的视频流
        "-map", "1:a:0",    # 使用第二个输入的音频流
        "-shortest",        # 以最短的流为准
        "-y",
        final_video_path
    ]
    
    try:
        subprocess.run(cmd, capture_output=True, check=True, text=True)
        print("视频音频替换完成")
        return final_video_path
        
    except subprocess.CalledProcessError as e:
        print(f"视频音频替换失败: {e.stderr}")
        raise RuntimeError(f"视频音频替换失败: {e.stderr}") from e



def sort_tts_files_by_index(tts_files: List[str]) -> List[str]:
    """根据文件名中的索引信息对TTS音频文件进行排序
    
    支持的文件名格式：
    - temp_05dd5441717c4ad6919ba91f327e1b0a_tts_segment_00018_beb0110e.wav
    - tts_0.wav, tts_1.wav 等
    - 其他包含数字索引的文件名
    
    Args:
        tts_files: TTS音频文件路径列表
        
    Returns:
        按索引排序的文件路径列表
    """
    def extract_index_from_filename(file_path: str) -> int:
        """从文件名中提取索引数字
        
        支持多种文件名格式：
        1. temp_xxx_tts_segment_00018_xxx.wav -> 提取 00018
        2. tts_0.wav -> 提取 0
        3. 其他包含数字的格式
        
        Args:
            file_path: 文件路径
            
        Returns:
            提取的索引数字，如果无法提取则返回0
        """
        filename = os.path.basename(file_path)
        
        # 匹配 temp_xxx_tts_segment_数字_xxx.wav 格式
        segment_match = re.search(r'_tts_segment_(\d+)_', filename)
        if segment_match:
            return int(segment_match.group(1))
        
        # 匹配 tts_数字.wav 格式
        tts_match = re.search(r'tts_(\d+)', filename)
        if tts_match:
            return int(tts_match.group(1))
        
        # 匹配其他包含数字的格式，取最后一个数字作为索引
        numbers = re.findall(r'\d+', filename)
        if numbers:
            return int(numbers[-1])  # 取最后一个数字
        
        # 如果无法提取数字，返回0
        print(f"警告：无法从文件名提取索引: {filename}")
        return 0
    
    # 按索引排序
    sorted_files = sorted(tts_files, key=extract_index_from_filename)
    
    # 打印排序结果用于调试
    print("TTS文件排序结果:")
    for i, file_path in enumerate(sorted_files):
        index = extract_index_from_filename(file_path)
        print(f"  {i}: 索引={index}, 文件={os.path.basename(file_path)}")
    
    return sorted_files


def cleanup_temp_files(file_paths: List[str]):
    """清理临时文件"""
    for file_path in file_paths:
        if file_path and os.path.exists(file_path):
            try:
                os.unlink(file_path)
            except OSError as e:
                print(f"清理临时文件失败 {file_path}: {e}")
