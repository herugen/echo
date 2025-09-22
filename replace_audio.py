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
import shutil


async def replace_audio_tracks(video_path: str, audio_path: str, segments_data: List[Dict[str, Any]], tts_audio_segments: List[str], task_id: str, background_volume: float = 0.15) -> str:
    """根据TTS音频替换视频中的音频轨道
    
    Args:
        video_path: 视频文件路径
        audio_path: 音频文件路径
        segments_data: 文本片段数据
        tts_audio_segments: TTS音频片段列表
        task_id: 任务ID
        background_volume: 背景音频音量比例（保留用于API兼容性）
    """
    print(f"开始音频替换任务，文本片段数量: {len(segments_data)}，TTS音频片段数量: {len(tts_audio_segments)}")
        
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

    # 从 MinIO 下载音频文件到临时位置
    temp_audio_path = storage.download_file(
        task_id=task_id,
        step="extract_audio",
        object_name=os.path.basename(audio_path)
    )
    if not temp_audio_path or not os.path.exists(temp_audio_path):
        raise ValueError("无法找到音频文件")
    
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
            task_id,
            temp_audio_path,
            segments_data,
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


async def create_mixed_audio(task_id: str, audio_path: str, segments_data: List[Dict[str, Any]], tts_files: List[str], background_volume: float = 0.15) -> str:
    """创建混合音频文件
    
    Args:
        audio_path: 音频文件路径
        segments_data: 文本片段数据
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
        await create_audio_by_subtitle_timing(task_id, audio_path, segments_data, tts_files, mixed_audio_path)
        print(f"音频拼接完成 {mixed_audio_path}")
        return mixed_audio_path
        
    except Exception as e:
        print(f"音频拼接失败: {e}")
        raise RuntimeError(f"音频拼接失败: {e}") from e


async def create_audio_by_subtitle_timing(task_id: str, audio_path: str, segments_data: List[Dict[str, Any]], tts_files: List[str], output_path: str):
    """根据字幕时间戳将TTS音频替换到原始音频中，支持时长误差处理
    
    Args:
        audio_path: 原始音频文件路径
        segments_data: 文本片段数据，包含start和end时间戳
        tts_files: TTS音频文件列表
        output_path: 输出音频文件路径
    """
    print("开始根据字幕时间戳替换音频，支持时长误差处理")
    
    if not tts_files:
        raise ValueError("没有TTS音频文件")
    
    if len(segments_data) != len(tts_files):
        print(f"警告：字幕片段数量({len(segments_data)})与TTS文件数量({len(tts_files)})不匹配")
    
    # 检测原始音频格式
    original_format = await probe_audio_format(audio_path)
    print(f"原始音频格式: 采样率={original_format['sample_rate']}Hz, 声道数={original_format['channels']}, 编码={original_format['codec']}")
    
    # 获取原始音频总时长
    original_duration = await probe_audio_duration(audio_path)
    print(f"原始音频时长: {original_duration:.2f}秒")
    
    # 创建临时文件列表
    temp_files = []
    
    storage = get_storage()

    try:
        # 使用新的时长同步方法处理音频替换
        await create_synchronized_audio_segments(
            task_id, audio_path, segments_data, tts_files, temp_files, 
            original_format, original_duration, storage, output_path
        )
        
        print(f"音频替换完成: {output_path}")
        return output_path
        
    finally:
        # 清理临时文件
        for temp_file in temp_files:
            if os.path.exists(temp_file):
                try:
                    os.unlink(temp_file)
                except OSError as e:
                    print(f"清理临时文件失败 {temp_file}: {e}")

async def convert_audio_format(input_file: str, target_format: Dict[str, Any]) -> str:
    """将音频转换为目标格式
    
    Args:
        input_file: 输入音频文件路径
        target_format: 目标格式字典，包含sample_rate、channels、codec
        
    Returns:
        转换后的音频文件路径
    """
    output_file = f"/tmp/converted_{uuid.uuid4().hex}.wav"
    
    cmd = [
        "ffmpeg", "-y",
        "-i", input_file,
        "-ar", str(target_format['sample_rate']),
        "-ac", str(target_format['channels']),
        "-c:a", target_format['codec'],
        output_file
    ]
    
    print(f"转换音频格式: {' '.join(cmd)}")
    subprocess.run(cmd, capture_output=True, text=True, check=True)
    return output_file


async def add_silence_to_tts(tts_file: str, silence_duration: float, master_format: Dict[str, Any]) -> str:
    """为TTS音频添加静音
    
    Args:
        tts_file: TTS音频文件路径
        silence_duration: 静音时长（秒）
        master_format: 主音频格式
        
    Returns:
        添加静音后的音频文件路径
    """
    output_file = f"/tmp/tts_with_silence_{uuid.uuid4().hex}.wav"
    silence_file = f"/tmp/silence_{uuid.uuid4().hex}.wav"
    
    try:
        # 生成静音
        silence_cmd = [
            "ffmpeg", "-y",
            "-f", "lavfi", "-i", f"anullsrc=duration={silence_duration}",
            "-ar", str(master_format['sample_rate']),
            "-ac", str(master_format['channels']),
            "-c:a", master_format['codec'],
            silence_file
        ]
        print(f"生成静音: {' '.join(silence_cmd)}")
        subprocess.run(silence_cmd, capture_output=True, text=True, check=True)
        
        # 拼接TTS和静音
        concat_cmd = [
            "ffmpeg", "-y",
            "-i", tts_file,
            "-i", silence_file,
            "-filter_complex", "[0:a][1:a]concat=n=2:v=0:a=1[out]",
            "-map", "[out]",
            "-ar", str(master_format['sample_rate']),
            "-ac", str(master_format['channels']),
            "-c:a", master_format['codec'],
            output_file
        ]
        print(f"拼接TTS和静音: {' '.join(concat_cmd)}")
        subprocess.run(concat_cmd, capture_output=True, text=True, check=True)
        
        return output_file
        
    finally:
        # 清理静音文件
        if os.path.exists(silence_file):
            try:
                os.unlink(silence_file)
            except OSError:
                pass


async def truncate_tts_audio(tts_file: str, target_duration: float, master_format: Dict[str, Any]) -> str:
    """截断TTS音频到指定时长
    
    Args:
        tts_file: TTS音频文件路径
        target_duration: 目标时长（秒）
        master_format: 主音频格式
        
    Returns:
        截断后的音频文件路径
    """
    output_file = f"/tmp/truncated_tts_{uuid.uuid4().hex}.wav"
    
    cmd = [
        "ffmpeg", "-y",
        "-i", tts_file,
        "-t", str(target_duration),  # 截断到指定时长
        "-ar", str(master_format['sample_rate']),
        "-ac", str(master_format['channels']),
        "-c:a", master_format['codec'],
        output_file
    ]
    
    print(f"截断TTS音频: {' '.join(cmd)}")
    subprocess.run(cmd, capture_output=True, text=True, check=True)
    return output_file


async def create_synchronized_audio_segments(
    task_id: str, audio_path: str, segments_data: List[Dict[str, Any]], 
    tts_files: List[str], temp_files: List[str],
    master_format: Dict[str, Any], original_duration: float, storage, output_path
):
    """创建时长同步的音频片段
    
    Args:
        task_id: 任务ID
        audio_path: 原始音频文件路径
        segments_data: 文本片段数据
        tts_files: TTS音频文件列表
        temp_files: 临时文件列表（用于存储处理后的片段）
        master_format: 主音频格式
        original_duration: 原始音频总时长
        storage: 存储实例
    """
    print("开始创建时长同步的音频片段")
    
    accumulated_error = 0.0  # 累积误差
    converted_tts_files = []  # 存储转换后的TTS文件
    
    try:
        # 第一步：转换所有TTS音频到标准格式
        print("转换TTS音频格式...")
        for i, tts_file in enumerate(tts_files):
            converted_file = await convert_audio_format(tts_file, master_format)
            converted_tts_files.append(converted_file)
            print(f"TTS文件 {i} 格式转换完成")
        
        # 第二步：处理每个片段的时长同步
        for i, (segment, converted_tts_file) in enumerate(zip(segments_data, converted_tts_files)):
            start_time = segment.get('start', 0)
            end_time = segment.get('end', start_time + 1)
            expected_duration = end_time - start_time
            
            # 检测转换后TTS的实际时长
            tts_duration = await probe_audio_duration(converted_tts_file)
            
            # 计算误差
            error = tts_duration - expected_duration
            accumulated_error += error
            
            print(f"片段 {i}: 预期时长={expected_duration:.2f}s, TTS时长={tts_duration:.2f}s, 误差={error:.2f}s, 累积误差={accumulated_error:.2f}s")
            
            # 处理时长差异
            final_audio = converted_tts_file
            
            if accumulated_error < -0.1:  # 需要静音填充（误差超过0.1秒）
                silence_duration = abs(accumulated_error)
                print(f"添加静音填充: {silence_duration:.2f}s")
                final_audio = await add_silence_to_tts(converted_tts_file, silence_duration, master_format)
                accumulated_error = 0.0  # 重置误差
            elif accumulated_error > 0:  # 误差较小，保留用于后续补偿
                print(f"保留误差用于后续补偿: {accumulated_error:.2f}s")
            

            # 使用FFmpeg进行音频替换，确保格式一致
            await replace_audio_segment_with_format_consistency(
                audio_path, final_audio, start_time, end_time, 
                output_path, master_format, original_duration
            )
            shutil.copyfile(output_path, audio_path)
            
            # 上传到MinIO
            object_name = f"segment_{i}_{uuid.uuid4().hex}.wav"
            storage.upload_file(
                task_id=task_id,
                step="replace_audio",
                local_file_path=output_path,
                object_name=object_name
            )
            print(f"片段 {i} 处理完成并上传")
    finally:
        # 清理转换后的TTS文件
        for converted_file in converted_tts_files:
            if os.path.exists(converted_file):
                try:
                    os.unlink(converted_file)
                except OSError as e:
                    print(f"清理转换文件失败 {converted_file}: {e}")


async def replace_audio_segment_with_format_consistency(
    audio_path: str, tts_file: str, start_time: float, end_time: float,
    output_path: str, master_format: Dict[str, Any], original_duration: float
):
    """使用格式一致性进行音频片段替换
    
    Args:
        audio_path: 原始音频文件路径
        tts_file: TTS音频文件路径
        start_time: 开始时间
        end_time: 结束时间
        output_path: 输出文件路径
        master_format: 主音频格式
        original_duration: 原始音频总时长
    """
    try:
        # 构建FFmpeg命令进行音频替换，确保格式一致
        cmd = [
            "ffmpeg", "-y",
            "-i", audio_path,  # 原始音频
            "-i", tts_file,    # TTS音频
            "-filter_complex", 
            f"[0:a]atrim=0:{start_time}[before];"
            f"[0:a]atrim={end_time}:{original_duration}[after];"
            f"[before][1:a][after]concat=n=3:v=0:a=1[out]",
            "-map", "[out]",
            "-c:a", master_format['codec'],
            "-ar", str(master_format['sample_rate']),
            "-ac", str(master_format['channels']),
            output_path
        ]
        
        print(f"执行格式一致的音频替换: {' '.join(cmd)}")
        subprocess.run(cmd, capture_output=True, text=True, check=True)
        print(f"音频片段替换完成: {output_path}")
        
    except subprocess.CalledProcessError as e:
        print(f"音频片段替换失败: {e.stderr}")
        # 如果替换失败，使用原始音频
        cmd_fallback = [
            "ffmpeg", "-y",
            "-i", audio_path,
            "-c:a", master_format['codec'],
            "-ar", str(master_format['sample_rate']),
            "-ac", str(master_format['channels']),
            output_path
        ]
        subprocess.run(cmd_fallback, capture_output=True, text=True, check=True)
        print(f"使用原始音频作为备选: {output_path}")


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
