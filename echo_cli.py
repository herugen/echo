#!/usr/bin/env python3
"""
智能重新运行脚本
自动检测已完成的任务，从第一个未完成的任务开始继续执行
"""

import asyncio
import sys
import os
from dotenv import load_dotenv
import json

load_dotenv()

# 添加当前目录到Python路径
sys.path.insert(0, os.path.dirname(__file__))

# 导入所有任务模块
from download_video import download_video
from extract_video_format import extract_video_format
from extract_audio import extract_audio
from speech_to_text import speech_to_text
from gen_subtitle import gen_subtitle
from gen_translated_subtitle import gen_translated_subtitle
from add_subtitle import add_subtitle_to_video
from add_translated_subtitle import add_translated_subtitle_to_video
from translate_text import translate_text
from split_audio import split_audio_by_subtitle
from generate_tts import generate_tts_audio_long
from replace_audio import replace_audio_tracks_all
from minio_storage import get_storage


async def check_task_status(task_id: str):
    """检查各个任务的完成状态"""
    storage = get_storage()
    
    # 定义任务检查顺序和对应的步骤名
    task_checks = [
        ("download", "下载视频", "download_video"),
        ("extract_video_format", "提取视频格式", "extract_video_format"),
        ("extract_audio", "提取音频", "extract_audio"),
        ("speech_to_text", "语音识别", "speech_to_text"),
        ("split_audio", "分割音频", "split_audio"),
        ("gen_subtitle", "生成字幕", "gen_subtitle"),
        ("translate_text", "文本翻译", "translate_text"),
        ("gen_translated_subtitle", "生成翻译后的字幕", "gen_translated_subtitle"),
        ("generate_tts", "TTS生成", "generate_tts"),
        ("replace_audio", "音频替换", "replace_audio")
    ]
    
    completed_tasks = []
    missing_tasks = []
    
    print(f"🔍 检查任务 {task_id} 的完成状态:")
    print("=" * 60)
    
    for step, description, task_name in task_checks:
        try:
            files = storage.list_files(task_id, step)
            if files:
                completed_tasks.append((step, description, task_name, files))
                print(f"✅ {description}: {len(files)} 个文件")
            else:
                missing_tasks.append((step, description, task_name))
                print(f"❌ {description}: 未完成")
        except (OSError, ValueError, RuntimeError) as e:
            missing_tasks.append((step, description, task_name))
            print(f"⚠️  {description}: 检查失败 - {e}")
    
    print("=" * 60)
    return completed_tasks, missing_tasks


async def echo(task_id: str, target_language: str = "zh", url: str = None):
    """智能重新运行工作流"""
    
    print(f"🚀 智能重新运行工作流，任务ID: {task_id}")
    print()
    
    # 检查任务状态
    completed_tasks, missing_tasks = await check_task_status(task_id)
    
    if not missing_tasks:
        print("🎉 所有任务都已完成！")
        return completed_tasks[-1][3][0] if completed_tasks else None
    
    print(f"\n📋 需要完成的任务: {len(missing_tasks)} 个")
    for _, description, _ in missing_tasks:
        print(f"   - {description}")
    
    print("\n🔄 开始执行未完成的任务...")
    print("=" * 60)
    
    storage = get_storage()
    
    try:
        # 获取已完成任务的输出
        video_path = None
        audio_path = None
        segments_data = None
        translated_segments = None
        subtitle_path = None
        translated_subtitle_path = None
        audio_segments = None
        tts_audio_path = None
        
        # 1. 下载视频 (如果需要)
        if any(task[0] == "download" for task in missing_tasks):
            if not url:
                print("❌ 需要提供视频URL来下载视频")
                return None
            print("📥 下载视频...")
            video_path = await download_video(url, task_id)
            print(f"✅ 视频下载完成: {os.path.basename(video_path)}")
        else:
            # 使用已下载的视频
            video_files = storage.list_files(task_id, "download")
            if video_files:
                video_path = video_files[0]["object_name"]
                print(f"✅ 使用已下载的视频: {os.path.basename(video_path)}")
        
        # 2. 提取视频格式 (如果需要)
        if any(task[0] == "extract_video_format" for task in missing_tasks):
            print("🎬 提取视频格式...")
            format_path = await extract_video_format(video_path, task_id)
            print(f"✅ 视频格式提取完成: {os.path.basename(format_path)}")
        else:
            # 使用已提取的视频格式
            format_files = storage.list_files(task_id, "extract_video_format")
            if format_files:
                format_path = format_files[0]["object_name"]
                print(f"✅ 使用已提取的视频格式: {os.path.basename(format_path)}")
        
        # 3. 提取音频 (如果需要)
        if any(task[0] == "extract_audio" for task in missing_tasks):
            print("🎵 提取音频...")
            audio_path = await extract_audio(video_path, task_id)
            print(f"✅ 音频提取完成: {os.path.basename(audio_path)}")
        else:
            # 使用已提取的音频
            audio_files = storage.list_files(task_id, "extract_audio")
            if audio_files:
                audio_path = audio_files[0]["object_name"]
                print(f"✅ 使用已提取的音频: {os.path.basename(audio_path)}")
        
        # 3. 语音识别 (如果需要)
        if any(task[0] == "speech_to_text" for task in missing_tasks):
            print("🗣️  语音识别...")
            speech_result = await speech_to_text(audio_path, task_id)
            segments_data = speech_result["segments"]
            print(f"✅ 语音识别完成，识别到 {len(segments_data)} 个片段")
        else:
            # 使用已识别的结果
            speech_files = storage.list_files(task_id, "speech_to_text")
            if speech_files:
                # 下载文件到临时位置
                temp_file = storage.download_file_by_path(speech_files[0]["object_name"])
                with open(temp_file, 'r', encoding='utf-8') as f:
                    speech_result = json.load(f)
                    segments_data = speech_result["segments"]
                print(f"✅ 使用已识别的结果: {len(segments_data)} 个片段")

        
        # 7. 分割音频 (如果需要)
        if any(task[0] == "split_audio" for task in missing_tasks):
            print("✂️  分割音频...")
            audio_segments = await split_audio_by_subtitle(audio_path, segments_data, task_id)
            print(f"✅ 音频分割完成，生成了 {len(audio_segments)} 个片段")
        else:
            # 使用已分割的音频
            split_files = storage.list_files(task_id, "split_audio")
            if split_files:
                audio_segments = [file_info["object_name"] for file_info in split_files]
                print(f"✅ 使用已分割的音频: {len(audio_segments)} 个片段")
        

        # 3.1. 生成字幕 (如果需要)
        if any(task[0] == "gen_subtitle" for task in missing_tasks):
            print("📝 生成字幕...")
            subtitle_path = await gen_subtitle(segments_data, task_id)
            if subtitle_path:
                print("✅ 字幕生成完成:")
                print(f"   - 字幕: {os.path.basename(subtitle_path)}")
            else:
                print("❌ 字幕生成失败")
                return
        else:
            # 使用已生成的字幕
            subtitle_files = storage.list_files(task_id, "gen_subtitle")
            if subtitle_files:
                # 构建字幕信息字典
                subtitle_file = None
                for file_info in subtitle_files:
                    subtitle_file = file_info["object_name"]
                
                if subtitle_file:
                    subtitle_path = subtitle_file
                    print("✅ 使用已生成的字幕:")
                    print(f"   - 字幕: {os.path.basename(subtitle_path)}")
                else:
                    print("❌ 未找到完整的字幕文件")
                    return

        # 5. 翻译文本 (如果需要)
        if any(task[0] == "translate_text" for task in missing_tasks):
            print(f"🌍 翻译文本 (目标语言: {target_language})...")
            translated_segments = await translate_text(segments_data, target_language, task_id)
            print("✅ 文本翻译完成")
        else:
            # 使用已翻译的结果
            translate_files = storage.list_files(task_id, "translate_text")
            if translate_files:
                # 下载文件到临时位置
                temp_file = storage.download_file_by_path(translate_files[0]["object_name"])
                with open(temp_file, 'r', encoding='utf-8') as f:
                    translated_segments = json.load(f)
                print("✅ 使用已翻译的结果")
        
        # 6. 生成字幕 (如果需要)
        if any(task[0] == "gen_translated_subtitle" for task in missing_tasks):
            print("📝 生成翻译后的字幕...")
            translated_subtitle_path = await gen_translated_subtitle(translated_segments, task_id, format_path)
            if translated_subtitle_path:
                print("✅ 翻译后的字幕生成完成:")
                print(f"   - 字幕: {os.path.basename(translated_subtitle_path)}")
            else:
                print("❌ 翻译后的字幕生成失败")
                return
        else:
            # 使用已生成的字幕
            subtitle_files = storage.list_files(task_id, "gen_translated_subtitle")
            if subtitle_files:
                # 构建字幕信息字典
                translated_subtitle_path = None
                for file_info in subtitle_files:
                    translated_subtitle_path = file_info["object_name"]
                
                if translated_subtitle_path:
                    translated_subtitle_path = subtitle_path
                    print("✅ 使用已生成的字幕:")
                    print(f"   - 字幕: {os.path.basename(translated_subtitle_path)}")
                else:
                    print("❌ 未找到完整的字幕文件")
                    return

        # 8. TTS生成 (如果需要)
        if any(task[0] == "generate_tts" for task in missing_tasks):
            print("🔊 TTS语音合成...")
            to_translate_segments = ""
            for segment in translated_segments:
                to_translate_segments += segment["text"] + "\n"
            tts_audio_path = await generate_tts_audio_long(to_translate_segments, target_language, audio_path, task_id)
            print(f"✅ TTS生成完成: {os.path.basename(tts_audio_path)}")
        else:
            # 使用已生成的TTS
            tts_files = storage.list_files(task_id, "generate_tts")
            if tts_files:
                tts_audio_path = tts_files[0]["object_name"]
                print(f"✅ 使用已生成的TTS: {os.path.basename(tts_audio_path)}")


        # 9. 替换音频 (如果需要)
        if any(task[0] == "replace_audio" for task in missing_tasks):
            print("🔄 替换音频...")
            final_video = await replace_audio_tracks_all(video_path, tts_audio_path, task_id)
            print(f"✅ 音频替换完成: {os.path.basename(final_video)}")
        else:
            # 使用已替换的音频
            replace_files = storage.list_files(task_id, "replace_audio")
            if replace_files:
                final_video = replace_files[0]["object_name"]
                print(f"✅ 使用已替换的音频: {os.path.basename(final_video)}")
        
        print("\n🎉 智能重新运行完成！")
        return final_video
        
    except (OSError, ValueError, RuntimeError) as e:
        print(f"\n❌ 重新运行失败: {e}")
        import traceback
        traceback.print_exc()
        return None


async def main():
    """主函数"""
    if len(sys.argv) < 2:
        print("用法: python echo_cli.py <task_id> [target_language] [url]")
        return
    
    task_id = sys.argv[1]
    target_language = sys.argv[2] if len(sys.argv) > 2 else "zh"
    url = sys.argv[3] if len(sys.argv) > 3 else None
    
    print(f"🆔 任务ID: {task_id}")
    print(f"🌍 目标语言: {target_language}")
    if url:
        print(f"🔗 视频URL: {url}")
    print()
    
    # 开始智能重新运行
    result = await echo(task_id, target_language, url)
    
    if result:
        print(f"\n🎉 成功！最终视频: {result}")
    else:
        print("\n💥 失败！请检查错误信息")


if __name__ == "__main__":
    asyncio.run(main())
