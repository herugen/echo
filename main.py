"""
视频翻译工作流服务
基于 Prefect 2.x 的工作流编排系统
"""

# =============================================================================
# 导入依赖
# =============================================================================
from fastapi import FastAPI, HTTPException, BackgroundTasks
from pydantic import BaseModel
from dotenv import load_dotenv
from prefect import flow, task
import uuid

# 导入任务模块
from download_video import download_video
from extract_audio import extract_audio
from speech_to_text import speech_to_text
from add_subtitle import add_subtitle_to_video
from translate_text import translate_text
from gen_subtitle import gen_subtitle
from split_audio import split_audio_by_subtitle
from generate_tts import generate_tts_audio
from replace_audio import replace_audio_tracks
from minio_storage import get_storage

# 加载环境变量
load_dotenv()

# =============================================================================
# FastAPI 应用初始化
# =============================================================================
async def startup():
    print("服务启动")
    _ = get_storage() # 初始化存储实例


app = FastAPI(title="视频翻译工作流服务", version="1.0.0")

@app.on_event("startup")
async def startup_event():
    await startup()

# =============================================================================
# 数据模型定义
# =============================================================================
class VideoTranslationRequest(BaseModel):
    """视频翻译请求"""
    url: str
    target_language: str = "zh"  # 目标语言

class VideoTranslationResponse(BaseModel):
    """视频翻译响应"""
    task_id: str
    status: str
    message: str

# =============================================================================
# 工作流任务定义
# =============================================================================

# -----------------------------------------------------------------------------
# 视频处理任务
# -----------------------------------------------------------------------------
@task
async def download_video_task(url: str, task_id: str) -> str:
    """使用 Cobalt 下载视频"""
    return await download_video(url, task_id)

@task
async def extract_audio_task(video_path: str, task_id: str) -> str:
    """使用 FFmpeg 提取音频"""
    return await extract_audio(video_path, task_id)

# -----------------------------------------------------------------------------
# 语音识别任务
# -----------------------------------------------------------------------------
@task
async def speech_to_text_task(audio_path: str, task_id: str):
    """使用 Fast-Whisper 进行语音识别，返回结构化数据"""
    return await speech_to_text(audio_path, task_id)

# -----------------------------------------------------------------------------
# 文本处理任务
# -----------------------------------------------------------------------------
@task
async def add_subtitle_to_video_task(subtitle_path: str, task_id: str):
    """给视频加上原生字幕"""
    return await add_subtitle_to_video(subtitle_path, task_id)

@task
async def translate_text_task(segments_data, target_language: str, task_id: str):
    """使用 DeepSeek 翻译文本片段"""
    return await translate_text(segments_data, target_language, task_id)

# -----------------------------------------------------------------------------
# 字幕和音频处理任务
# -----------------------------------------------------------------------------
@task
async def generate_subtitle_task(segments_data, task_id: str):
    """生成 SRT 字幕文件"""
    return await gen_subtitle(segments_data, task_id)

@task
async def split_audio_task(audio_path: str, subtitle_path: str, task_id: str):
    """根据字幕时间分割音频"""
    return await split_audio_by_subtitle(audio_path, subtitle_path, task_id)

@task
async def generate_tts_task(text_segments, target_language: str, task_id: str):
    """使用 TTS 生成翻译后的音频"""
    return await generate_tts_audio(text_segments, target_language, task_id)

@task
async def replace_audio_task(video_path: str, original_audio_segments, tts_audio_segments, task_id: str):
    """替换视频中的音频轨道"""
    return await replace_audio_tracks(video_path, original_audio_segments, tts_audio_segments, task_id)

# =============================================================================
# 主工作流
# =============================================================================
@flow(name="video_translation_workflow")
async def video_translation_workflow(
    task_id: str,
    url: str, 
    target_language: str = "zh"
) -> str:
    """视频翻译主工作流"""
    print(f"开始视频翻译工作流，任务ID: {task_id}")
    
    # 1. 下载视频
    video_path = await download_video_task(url, task_id)
    
    # 2. 提取音频
    audio_path = await extract_audio_task(video_path, task_id)
    
    # 3. 语音识别
    speech_result = await speech_to_text_task(audio_path, task_id)
    segments_data = speech_result["segments"]
    
    # 4. 生成字幕
    subtitle_path = await generate_subtitle_task(segments_data, task_id)
    
    # 5. 生成带字幕的中间视频文件
    subtitled_video_path = await add_subtitle_to_video_task(subtitle_path, task_id)
    if subtitled_video_path:
        print(f"带字幕的中间视频已生成: {subtitled_video_path}")

    # 7. 翻译文本
    translated_segments = await translate_text_task(corrected_segments, target_language, task_id)
    
    # 8. 分割音频
    audio_segments = await split_audio_task(audio_path, subtitle_path, task_id)
    
    # 9. TTS 生成
    tts_segments = await generate_tts_task(translated_segments, target_language, task_id)
    
    # 10. 替换音频
    final_video = await replace_audio_task(video_path, audio_segments, tts_segments, task_id)
    
    print(f"视频翻译工作流完成，任务ID: {task_id}")
    return final_video

# =============================================================================
# API 端点
# =============================================================================
@app.post("/translate", response_model=VideoTranslationResponse)
async def start_translation(request: VideoTranslationRequest, background_tasks: BackgroundTasks):
    """启动视频翻译工作流"""
    try:
        # 生成任务ID
        task_id = f"task_{uuid.uuid4().hex[:8]}"
        
        # 使用background_tasks在后台执行工作流
        background_tasks.add_task(video_translation_workflow, task_id, request.url, request.target_language)
        
        return VideoTranslationResponse(
            task_id=task_id,
            status="pending",
            message="翻译任务已启动，正在后台执行"
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e)) from e

@app.get("/health")
async def health_check():
    """健康检查"""
    return {"status": "healthy", "service": "video_translation_workflow"}

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
