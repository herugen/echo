# Echo CLI 重构方案

## 目标
- 移除 Prefect/FastAPI/MinIO 依赖，简化为本地同步 CLI 工具
- 顺序执行完整的视频翻译管线，控制台输出进度，命令返回值表示成功/失败
- 所有中间产物保存在结构化的本地目录中，支持重试/复用

## 整体架构
- `echo_cli.py`：CLI 入口（Typer/Click 均可），提供 `translate`、`list-runs`、`show-run` 等子命令
- `pipeline/config.py`：`PipelineConfig` dataclass，集中管理 url、目标语言、模型、服务地址、缓存策略等
- `pipeline/context.py`：负责 run 目录生命周期、路径生成、metadata 记录
- `pipeline/stages/*.py`：每个阶段一个同步函数，参数/返回值均为 Python 数据或 `pathlib.Path`
- `pipeline/pipeline.py`：`run_pipeline(config)` 串联各阶段，处理日志、异常、结果汇总

## 本地存储策略
- 根目录 `runs/`
- 每次执行创建 `runs/<slug>/<yyyyMMdd-HHmmss>-<short-hash>/`
- 目录结构：
  - `raw/`：原始视频
  - `audio/`：提取音频与分段
  - `transcripts/`：STT JSON/SRT
  - `translations/`：翻译结果与字幕
  - `tts/`：TTS 片段
  - `video/`：最终视频及替换产物
  - `logs/`：`metadata.json`、阶段日志、调试信息
  - `tmp/`：处理过程中的临时文件（可删除）

## 命名与复用
- 命名统一：`seg_0001.wav`、`subtitle_0001.srt`、`translated_final_v1.mp4`
- 通过 `metadata.json` 记录输入参数、生成文件、耗时，供 CLI 查询
- CLI 提供 `--reuse <run-id>` 跳过已有阶段（如下载/STT），`--force` 强制重新计算

## 日志与进度
- 使用 `rich`/`tqdm` 输出阶段进度、关键信息
- 同步写入 `logs/stages.log`（JSON Lines），失败时打印最后阶段的错误并指向 run 目录
- `--keep-temp` 保留 `tmp/`，默认在流程结束后清理临时文件

## CLI 功能建议
- `echo translate --url <video> --lang zh [--job-name foo] [--reuse run-id] [--keep-temp] [--force stage]`
- `echo list-runs`：列出历史执行，状态/时间/输入
- `echo show-run <run-id>`：查看指定 run 的 artefact 路径与 metadata

## 分阶段迁移建议
1. 新建 pipeline 框架与目录结构
2. 将现有 stage 逻辑迁移为同步函数并移除 `async`、Prefect 装饰器
3. 替换 MinIO 读写为本地路径操作
4. 实现 CLI 命令、日志输出与 run 目录管理
5. 补充 10~20 秒示例视频的端到端集成测试，保证 artefact 生成正确

