"""
字幕生成任务
使用修正后的segments生成字幕文件，并保存到MinIO
"""

import os
import uuid
import tempfile
from typing import List, Dict, Any
from minio_storage import get_storage


async def gen_subtitle(segments_data: List[Dict[str, Any]], task_id: str) -> :
    """
    使用修正后的segments生成字幕文件，并保存到MinIO
    
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
        
        # 从MinIO下载原始视频文件
        # 原始视频文件存储在download步骤中
        video_files = storage.list_files(task_id, "download")
        if not video_files:
            print("未找到原始视频文件")
            return None
        
        # 生成横屏和竖屏两套字幕文件
        print("生成横屏字幕文件...")
        landscape_content = generate_ass_from_segments(segments_data, 'landscape')
        
        print("生成竖屏字幕文件...")
        portrait_content = generate_ass_from_segments(segments_data, 'portrait')
        
        # 创建横屏字幕文件
        landscape_path = os.path.join(tempfile.gettempdir(), f"subtitle_landscape_{task_id}_{uuid.uuid4().hex}.ass")
        with open(landscape_path, 'w', encoding='utf-8') as f:
            f.write(landscape_content)
        
        # 创建竖屏字幕文件
        portrait_path = os.path.join(tempfile.gettempdir(), f"subtitle_portrait_{task_id}_{uuid.uuid4().hex}.ass")
        with open(portrait_path, 'w', encoding='utf-8') as f:
            f.write(portrait_content)
        
        # 上传横屏字幕到MinIO
        landscape_object_name = f"subtitle_landscape_{uuid.uuid4().hex}.ass"
        landscape_minio_path = storage.upload_file(
            task_id=task_id,
            step="gen_subtitle",
            local_file_path=landscape_path,
            object_name=landscape_object_name
        )
        
        # 上传竖屏字幕到MinIO
        portrait_object_name = f"subtitle_portrait_{uuid.uuid4().hex}.ass"
        portrait_minio_path = storage.upload_file(
            task_id=task_id,
            step="gen_subtitle",
            local_file_path=portrait_path,
            object_name=portrait_object_name
        )
        
        # 清理临时文件
        try:
            os.unlink(landscape_path)
            os.unlink(portrait_path)
        except OSError as e:
            print(f"清理临时文件时出错: {e}")
        
        print(f"横屏字幕文件已生成: {landscape_minio_path}")
        print(f"竖屏字幕文件已生成: {portrait_minio_path}")
        
        # 返回字幕文件信息
        return {
            "landscape": landscape_minio_path,
            "portrait": portrait_minio_path
        }
        
    except (OSError, ValueError, RuntimeError) as e:
        print(f"生成字幕文件失败: {str(e)}")
        return None


def generate_ass_from_segments(segments_data: List[Dict[str, Any]], orientation: str = 'landscape') -> str:
    """
    从segments数据生成ASS字幕内容，支持word级别高亮
    
    Args:
        segments_data: 文本片段数据，包含words字段
        orientation: 视频方向 ('portrait' 或 'landscape')
        
    Returns:
        str: ASS格式的字幕内容
    """
    # ASS文件头部 - 针对竖屏视频优化，修复多行背景重叠问题
    ass_content = """[Script Info]
Title: Word-level Highlighted Subtitles for Vertical Video
ScriptType: v4.00+
WrapStyle: 0
ScaledBorderAndShadow: yes
YCbCr Matrix: TV.601

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: Default,Arial,12,&H00000000,&H000000FF,&H00000000,&H8000FFFF,1,0,0,0,100,100,0,0,1,2,2,2,2,30,30,40,1
Style: Highlight,Arial,12,&H00000000,&H000000FF,&H00000000,&H8000FFFF,1,0,0,0,100,100,0,0,1,2,2,2,2,30,30,40,1
Style: DefaultPortrait,Arial,8,&H00000000,&H000000FF,&H00000000,&H8000FFFF,1,0,0,0,100,100,0,0,1,2,2,2,2,25,25,35,1
Style: HighlightPortrait,Arial,8,&H00000000,&H000000FF,&H00000000,&H8000FFFF,1,0,0,0,100,100,0,0,1,2,2,2,2,25,25,35,1
Style: MultiLineDefault,Arial,12,&H00000000,&H000000FF,&H00000000,&H8000FFFF,1,0,0,0,100,100,0,0,1,1,1,2,2,30,30,40,1
Style: MultiLineHighlight,Arial,12,&H00000000,&H000000FF,&H00000000,&H8000FFFF,1,0,0,0,100,100,0,0,1,1,1,2,2,30,30,40,1
Style: MultiLinePortrait,Arial,8,&H00000000,&H000000FF,&H00000000,&H8000FFFF,1,0,0,0,100,100,0,0,1,1,1,2,2,25,25,35,1
Style: MultiLineHighlightPortrait,Arial,8,&H00000000,&H000000FF,&H00000000,&H8000FFFF,1,0,0,0,100,100,0,0,1,1,1,2,2,25,25,35,1

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
"""
    
    # 根据视频方向选择样式
    default_style = "DefaultPortrait" if orientation == 'portrait' else "Default"
    highlight_style = "HighlightPortrait" if orientation == 'portrait' else "Highlight"
    
    # 收集所有word级别数据，按时间排序
    all_words = []
    for segment in segments_data:
        if "words" in segment and segment["words"]:
            for word in segment["words"]:
                if word.get("word", "").strip():
                    all_words.append({
                        "word": word.get("word", "").strip(),
                        "start": word.get("start", 0),
                        "end": word.get("end", word.get("start", 0) + 1),
                        "probability": word.get("probability", 0),
                        "segment_text": segment.get("text", "").strip()
                    })
    
    if all_words:
        # 按时间排序
        all_words.sort(key=lambda x: x["start"])
        
        # 生成基于word的精确字幕
        ass_content += generate_word_based_subtitles(all_words, highlight_style, orientation)
    else:
        # 没有word数据时，回退到segment级别
        for segment in segments_data:
            if not segment.get("text", "").strip():
                continue
                
            start_time = format_ass_timestamp(segment["start"])
            end_time = format_ass_timestamp(segment["end"])
            text = segment["text"].strip()
            ass_content += f"Dialogue: 0,{start_time},{end_time},{default_style},,0,0,0,,{text}\n"
    
    return ass_content


def generate_word_based_subtitles(all_words: List[Dict], highlight_style: str, orientation: str = 'landscape') -> str:
    """
    基于句子分段生成稳定的字幕，避免闪烁问题
    
    Args:
        all_words: 所有word数据，已按时间排序
        highlight_style: 高亮样式名称
        orientation: 视频方向 ('portrait' 或 'landscape')
        
    Returns:
        str: ASS格式的字幕内容
    """
    dialogue_lines = []
    
    # 将words按句子分组
    sentence_groups = group_words_by_sentences(all_words)
    
    for i, sentence_group in enumerate(sentence_groups):
        if not sentence_group:
            continue
            
        # 计算整个句子的时间范围
        sentence_start = min(word["start"] for word in sentence_group)
        sentence_end = max(word["end"] for word in sentence_group)
        
        # 添加缓冲时间，避免句子间重叠
        if i > 0:
            # 确保与前一个句子有至少0.1秒的间隔
            sentence_start = max(sentence_start, sentence_start + 0.1)
        
        # 为句子添加适当的显示时间（至少1秒）
        min_duration = 1.0
        if sentence_end - sentence_start < min_duration:
            sentence_end = sentence_start + min_duration
        
        # 为每个词生成黄色背景高亮字幕
        highlighted_sentence = create_highlighted_sentence(sentence_group)
        
        # 检测是否需要多行显示
        sentence_text = build_sentence_text(sentence_group)
        is_multiline = len(sentence_text) > 50  # 如果句子超过50个字符，可能需要换行
        
        # 根据是否需要多行显示选择样式
        if is_multiline:
            if orientation == 'portrait':
                current_style = "MultiLineHighlightPortrait"
            else:
                current_style = "MultiLineHighlight"
        else:
            current_style = highlight_style
        
        # 生成一个字幕行，显示整个句子
        start_time = format_ass_timestamp(sentence_start)
        end_time = format_ass_timestamp(sentence_end)
        
        dialogue_lines.append(f"Dialogue: 0,{start_time},{end_time},{current_style},,0,0,0,,{highlighted_sentence}")
    
    return "\n".join(dialogue_lines) + "\n"


def group_words_by_sentences(all_words: List[Dict]) -> List[List[Dict]]:
    """
    将words按句子边界分组，并智能分割过长的句子
    
    Args:
        all_words: 所有word数据
        
    Returns:
        List[List[Dict]]: 按句子分组的words
    """
    sentence_groups = []
    current_sentence = []
    
    for word in all_words:
        word_text = word["word"].strip()
        if not word_text:
            continue
            
        current_sentence.append(word)
        
        # 检查是否是句子结束
        if word_text.endswith(('.', '!', '?', '。', '！', '？')):
            if current_sentence:
                # 智能分割过长的句子
                split_sentences = split_long_sentence(current_sentence)
                sentence_groups.extend(split_sentences)
                current_sentence = []
    
    # 添加最后一个句子（如果有的话）
    if current_sentence:
        split_sentences = split_long_sentence(current_sentence)
        sentence_groups.extend(split_sentences)
    
    return sentence_groups


def split_long_sentence(sentence_words: List[Dict], max_words: int = 15) -> List[List[Dict]]:
    """
    智能分割过长的句子
    
    Args:
        sentence_words: 句子中的words
        max_words: 每个片段的最大词数
        
    Returns:
        List[List[Dict]]: 分割后的句子片段
    """
    if len(sentence_words) <= max_words:
        return [sentence_words]
    
    # 查找合适的分割点（逗号、分号等）
    split_points = []
    for i, word in enumerate(sentence_words):
        word_text = word["word"].strip()
        if word_text.endswith((',', ';', ':', '，', '；', '：')):
            split_points.append(i)
    
    # 如果没有标点符号，按词数强制分割
    if not split_points:
        result = []
        for i in range(0, len(sentence_words), max_words):
            result.append(sentence_words[i:i + max_words])
        return result
    
    # 根据标点符号智能分割
    result = []
    start = 0
    
    for split_point in split_points:
        if split_point - start <= max_words:
            result.append(sentence_words[start:split_point + 1])
            start = split_point + 1
        else:
            # 如果当前片段太长，强制分割
            while start < split_point:
                end = min(start + max_words, split_point + 1)
                result.append(sentence_words[start:end])
                start = end
    
    # 处理剩余部分
    if start < len(sentence_words):
        result.append(sentence_words[start:])
    
    return result


def build_sentence_text(sentence_words: List[Dict]) -> str:
    """
    构建完整的句子文本
    
    Args:
        sentence_words: 句子中的words
        
    Returns:
        str: 完整的句子文本
    """
    result = []
    for i, word in enumerate(sentence_words):
        word_text = word["word"].strip()
        if not word_text:
            continue
            
        if result:
            # 智能添加空格
            prev_word = sentence_words[i-1]["word"].strip()
            if not prev_word.endswith(('.', ',', '!', '?', ';', ':', '-', '—')):
                result.append(" ")
        
        result.append(word_text)
    
    return "".join(result)

def create_highlighted_sentence(sentence_words: List[Dict]) -> str:
    """
    创建带有词高亮的句子文本
    
    Args:
        sentence_words: 句子中的words
        
    Returns:
        str: 带有高亮效果的句子文本
    """
    result = []
    for i, word in enumerate(sentence_words):
        word_text = word["word"].strip()
        if not word_text:
            continue
            
        if result:
            # 智能添加空格
            prev_word = sentence_words[i-1]["word"].strip()
            if not prev_word.endswith(('.', ',', '!', '?', ';', ':', '-', '—')):
                result.append(" ")
        
        # 为每个词添加高亮效果
        highlighted_word = f"{{\\1c&H00FFFF&}}{word_text}{{\\1c&HFFFFFF&}}"
        result.append(highlighted_word)
    
    return "".join(result)


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
