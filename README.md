# Echo CLI 视频翻译工具

一个基于命令行的本地视频翻译工具，支持将视频中的语音翻译成目标语言、生成字幕并输出替换音频后的新视频。

## 功能特性

- 🎥 自动下载视频文件
- 🎵 提取音频轨道
- 🗣️ 语音识别转文字
- ✏️ AI 修正识别错误
- 🌍 多语言翻译
- 📝 生成字幕文件
- 🔊 TTS 语音合成
- 🎬 生成最终翻译视频

## 技术栈

- **CLI 框架**: Typer
- **音视频处理**: FFmpeg
- **语音识别**: WhisperX
- **AI 服务**: DeepSeek API（可选）

## 快速开始

### 1. 克隆项目
```bash
git clone <repository-url>
cd echo
```

### 2. 安装依赖
```bash
pip install -r requirements.txt
```

### 3. 构建 WhisperX Docker 镜像
WhisperX 及其依赖较为复杂，已封装为独立的 Docker 镜像。首次使用前需要构建：

```bash
./build.sh
# 或者手动执行
docker build -t whisperx-runner:latest docker/whisperx
```

### 4. 准备 FFmpeg/FFprobe
确保系统已安装 FFmpeg 和 FFprobe，并在 `PATH` 中可用。

### 5. 配置环境变量（可选）
在项目根目录创建 `.env`：
```bash
DEEPSEEK_API_KEY=your_api_key
TTS_SERVICE_URL=https://your-tts-service
# WhisperX 运行镜像与缓存目录（可选）
WHISPER_DOCKER_IMAGE=whisperx-runner:latest
WHISPER_CACHE_DIR=/absolute/path/to/cache
WHISPER_DOCKER_ARGS=--gpus all  # 如果需要 GPU
```

### 6. 运行翻译
```bash
python cli.py translate --url https://example.com/video.mp4 --lang zh
# 或使用本地文件
python cli.py translate --local-video ./sample.mp4 --lang en
```

默认将在 `runs/<slug>/<timestamp-hash>/` 下输出所有中间产物与最终视频。

## CLI 命令

- `python cli.py translate ...` 启动翻译流程
- `python cli.py list-runs` 查看历史运行
- `python cli.py show-run <path>` 查看指定运行的 metadata

## 目录结构

`runs/<slug>/<run-id>/` 下包含：

- `raw/` 原始视频
- `audio/` 提取音频与分段
- `transcripts/` 识别结果与字幕
- `translations/` 翻译结果与字幕
- `tts/` 生成的语音片段
- `video/` 最终视频
- `logs/metadata.json` 运行配置与 Artefacts 列表

## 工作流程

1. 下载或复制视频到 `raw/`
2. 提取视频格式信息
3. 提取原音频并分割
4. 使用 WhisperX 识别语音生成字幕
5. 调用 DeepSeek 翻译文本（如配置了 API Key）
6. 生成原文与翻译字幕文件
7. 调用 TTS 合成语音（如果配置 TTS 服务）
8. 使用新音频替换原视频音轨，输出最终视频

## 注意事项

- DeepSeek/TTS 服务均为可选功能，未配置时将跳过对应步骤
- `--keep-temp` 可保留临时文件用于调试
- `runs/` 目录可能快速增长，定期清理旧 run

## 快速开始

### 1. 克隆项目
```bash
git clone <repository-url>
cd echo
```

### 2. 启动服务
```bash
# 构建并启动所有服务
docker compose up -d

# 查看服务状态
docker compose ps
```

### 3. 访问服务
- **API 文档**: http://localhost:8000/docs
- **Prefect UI**: http://localhost:4200
- **健康检查**: http://localhost:8000/health

### 4. 测试 API
```bash
curl -X POST "http://localhost:8000/translate" \
  -H "Content-Type: application/json" \
  -d '{
    "url": "https://example.com/video.mp4",
    "target_language": "zh"
  }'
```

## 工作流程

1. **接收请求**: 用户通过 HTTP API 提交视频链接
2. **下载视频**: 使用 yt-dlp 下载视频文件
3. **提取音频**: 使用 FFmpeg 提取音频轨道（WAV 格式，44.1kHz，立体声）
4. **语音识别**: 使用 Docker 封装的 WhisperX 进行语音转文字
5. **文本修正**: 使用 DeepSeek 修正识别错误
6. **文本翻译**: 使用 DeepSeek 翻译到目标语言
7. **生成字幕**: 创建 SRT 字幕文件
8. **分割音频**: 根据字幕时间分割音频片段
9. **TTS 合成**: 生成翻译后的语音片段
10. **音频替换**: 将翻译后的语音替换到原视频
11. **输出结果**: 生成最终的翻译视频

## 配置说明

### 环境变量
创建 `.env` 文件并配置以下变量：

```bash
# Prefect 配置
PREFECT_API_URL=http://localhost:4200/api

# 数据库配置
DATABASE_URL=postgresql://prefect:prefect@postgres:5432/prefect
REDIS_URL=redis://redis:6379

# AI 服务配置
DEEPSEEK_API_KEY=your_api_key
TTS_SERVICE_URL=your_tts_service_url
```

## 开发指南

### 本地开发
```bash
# 安装依赖
pip install -r requirements.txt

# 启动 Prefect 服务器
prefect server start

# 启动应用
python main.py
```

### 添加新的工作流任务
1. 使用 `@task` 装饰器定义任务函数
2. 在 `@flow` 函数中调用任务
3. 设置任务间的依赖关系

## 部署说明

### 生产环境部署
1. 配置环境变量
2. 设置数据库连接
3. 配置 AI 服务 API 密钥
4. 启动 Docker 服务

### 监控和日志
- Prefect UI 提供工作流监控
- 应用日志存储在容器中
- 支持日志聚合和分析

## 注意事项

- 确保有足够的存储空间处理视频文件
- 配置合适的 AI 服务 API 限制
- 监控系统资源使用情况
- 定期清理临时文件

## 许可证

MIT License
