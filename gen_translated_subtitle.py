"""
字幕生成任务
使用修正后的segments生成字幕文件，并保存到MinIO
"""

import os
import uuid
import tempfile
from typing import List, Dict, Any
from minio_storage import get_storage


async def gen_translated_subtitle(segments_data: List[Dict[str, Any]], task_id: str, video_width: int) -> str:
    """
    使用翻译后的segments生成字幕文件，并保存到MinIO
    
    Args:
        segments_data: 文本片段数据
        task_id: 任务ID
        
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
        
        ass_content = generate_ass_from_segments(segments_data, video_width)

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


def generate_ass_from_segments(segments_data: List[Dict[str, Any]], video_width: int = 1920) -> str:
    """
    从翻译后的segments数据生成ASS字幕内容，使用segment级别显示翻译文本
    
    Args:
        segments_data: 翻译后的文本片段数据，只使用text字段，忽略words字段
        
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
Style: Default,Arial,12,&H0000FFFF,&H0000FFFF,&H00000000,&H8000FFFF,1,0,0,0,100,100,0,0,1,2,0,0,2,10,10,20,1

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

        # 根据视频宽度、边距和字体大小自动换行字幕文本（适配中文字体）
        # --------------------------------------------------------------------
        # 背景说明:
        #   - 中文字体（如思源黑体、微软雅黑等）每个汉字宽度约等于字体大小
        #   - 英文字符宽度约为字体大小的0.5倍
        #   - 需根据视频宽度、边距、字体大小估算每行可容纳的最大“宽度”，对text进行分行
        #   - 这里假设所有中文字符宽度为fontsize，英文及数字为fontsize*0.5
        # --------------------------------------------------------------------
        # 1. 设定边距和字体大小
        margin_l = margin_r = 10
        fontsize = 40

        # 2. 计算可用显示宽度（像素）
        available_width = video_width - margin_l - margin_r

        # 3. 计算每行最大“宽度”单位（以像素为单位）
        max_line_width = available_width
        lines = split_text_chinese(text, max_line_width, fontsize)
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
def split_text_chinese(text, max_width, fontsize):
    lines = []
    current_line = ""
    current_width = 0
    chinese_char_count = 0  # 中文字符计数
    
    for char in text:
        # 判断是否为中文字符
        if '\u4e00' <= char <= '\u9fff':
            chinese_char_count += 1
            char_w = fontsize
        elif char == '\n':
            lines.append(current_line)
            current_line = ""
            current_width = 0
            chinese_char_count = 0
            continue
        else:
            char_w = fontsize * 0.5
        
        # 检查是否超过15个中文字符
        if chinese_char_count > 15:
            if current_line:
                lines.append(current_line)
            current_line = char
            current_width = char_w
            chinese_char_count = 1 if '\u4e00' <= char <= '\u9fff' else 0
        elif current_width + char_w > max_width:
            if current_line:
                lines.append(current_line)
            current_line = char
            current_width = char_w
            chinese_char_count = 1 if '\u4e00' <= char <= '\u9fff' else 0
        else:
            current_line += char
            current_width += char_w
    
    if current_line:
        lines.append(current_line)
    return lines