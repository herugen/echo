"""
字幕生成任务
使用修正后的segments生成字幕文件，并保存到MinIO
"""

import os
import uuid
import tempfile
import json
from typing import List, Dict, Any
from minio_storage import get_storage


async def gen_translated_subtitle(segments_data: List[Dict[str, Any]], task_id: str, format_path: str) -> str:
    """
    使用翻译后的segments生成字幕文件，并保存到MinIO
    
    Args:
        segments_data: 文本片段数据
        task_id: 任务ID
        format_path: 视频格式信息文件路径
    Returns:
        str: 字幕文件在MinIO中的路径
    """
    try:
        print(f"开始生成字幕文件，共 {len(segments_data)} 个片段")
        
        if not segments_data:
            print("没有文本片段，跳过字幕文件生成")
            return None
        
        # 获取存储实例
        storage = get_storage()

        if not format_path:
            print("未找到视频格式信息文件")
            return None

        # 从MinIO下载视频格式信息文件
        format_file_path = storage.download_file_by_path(format_path)
        if not format_file_path:
            print("未找到视频格式信息文件")
            return None

        # 读取并解析JSON文件
        try:
            with open(format_file_path, 'r', encoding='utf-8') as f:
                format_info = json.load(f)
        except (json.JSONDecodeError, FileNotFoundError) as e:
            print(f"读取视频格式信息文件失败: {e}")
            return None
        video_width = format_info["width"]
        video_height = format_info["height"]
        is_vertical = False
        if video_height > video_width:
            is_vertical = True
        
        print(f"视频格式信息: {format_info}，视频方向: {is_vertical}")

        ass_content = generate_ass_from_segments(segments_data, is_vertical)

        # 创建横屏字幕文件
        ass_path = os.path.join(tempfile.gettempdir(), f"subtitle_{task_id}_{uuid.uuid4().hex}.ass")
        with open(ass_path, 'w', encoding='utf-8') as f:
            f.write(ass_content)
        
        # 上传横屏字幕到MinIO
        object_name = f"subtitle_{uuid.uuid4().hex}.ass"
        minio_path = storage.upload_file(
            task_id=task_id,
            step="gen_translated_subtitle",
            local_file_path=ass_path,
            object_name=object_name
        )
        
        # 清理临时文件
        try:
            os.unlink(ass_path)
        except OSError as e:
            print(f"清理临时文件时出错: {e}")
        
        print(f"横屏字幕文件已生成: {minio_path}")
        
        # 返回字幕文件信息
        return minio_path
        
    except (OSError, ValueError, RuntimeError) as e:
        print(f"生成字幕文件失败: {str(e)}")
        return None


def generate_ass_from_segments(segments_data: List[Dict[str, Any]], is_vertical: bool) -> str:
    """
    从翻译后的segments数据生成ASS字幕内容，使用segment级别显示翻译文本
    
    Args:
        segments_data: 翻译后的文本片段数据，只使用text字段，忽略words字段
        is_vertical: 是否为竖屏
    Returns:
        str: ASS格式的字幕内容
    """
    # ASS文件头部
    ass_content = """[Script Info]
Title: Word-level Highlighted Subtitles for Vertical Video
ScriptType: v4.00+
WrapStyle: 0
ScaledBorderAndShadow: yes
YCbCr Matrix: TV.601

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: Default,Arial,12,&H0000FFFF,&H0000FFFF,&H00000000,&H8000FFFF,1,0,0,0,100,100,0,0,1,2,0,0,5,10,10,20,1

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
"""
    
    # 根据视频方向选择样式
    default_style = "Default"
    
    # 翻译后的segments直接使用segment级别，忽略words字段
    for segment in segments_data:
        if not segment.get("text", "").strip():
            continue
            
        start_time = format_ass_timestamp(segment["start"])
        end_time = format_ass_timestamp(segment["end"])
        text = segment["text"].strip()

        # 根据视频方向，按照max_char_count切割
        lines = split_text_chinese(text, is_vertical)
        text = r"\N".join(lines)  # ASS换行符

        ass_content += f"Dialogue: 0,{start_time},{end_time},{default_style},,10,10,20,,{text}\n"
    
    return ass_content

def format_ass_timestamp(seconds: float) -> str:
    """
    将秒数转换为ASS时间戳格式 (H:MM:SS.CC)
    
    Args:
        seconds: 秒数
        
    Returns:
        str: 格式化的时间戳
    """
    hours = int(seconds // 3600)
    minutes = int((seconds % 3600) // 60)
    secs = int(seconds % 60)
    centisecs = int((seconds % 1) * 100)
    
    return f"{hours}:{minutes:02d}:{secs:02d}.{centisecs:02d}"


# 按最大宽度对text进行分行（中文宽，英文半宽）
def split_text_chinese(text, is_vertical):
    lines = []
    max_char_count = 15 if is_vertical else 45
    print(f"每行最大中文字数: {max_char_count}")

    # 根据中文字数，按照max_char_count切割
    # 说明:
    #   - 只统计中文字符（范围：\u4e00-\u9fff），遇到max_char_count就换行
    #   - 其他字符（如英文、标点）直接跟随，不计入chinese_char_count
    #   - 保证每行最多max_char_count个中文，其余自动分行
    current_line = ""
    chinese_count = 0
    for char in text:
        # 判断是否为中文字符
        if '\u4e00' <= char <= '\u9fff':
            chinese_count += 1
        current_line += char
        if chinese_count >= max_char_count:
            lines.append(current_line)
            current_line = ""
            chinese_count = 0
    if current_line:
        lines.append(current_line)

    return lines