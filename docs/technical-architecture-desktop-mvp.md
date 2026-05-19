# 本地视频理解与加工工具｜技术架构设计（Desktop MVP，保留未来 CLI 扩展）

## 1. 设计目标

### 1.1 当前目标
MVP 只交付 **Windows 11 Desktop App**，完成：
- 本地视频导入。
- 在线视频 URL 获取。
- 本地 GPU 转写。
- 翻译与字幕生成。
- 最终视频与字幕文件输出。
- 任务进度、失败原因、重试、历史任务。

### 1.2 架构目标
虽然 MVP 只有 Desktop，但从第一天起必须保证：
1. **核心能力不依赖 Desktop UI。**
2. **任务模型、流水线、产物规范未来可被 CLI 直接复用。**
3. **UI、应用编排、领域逻辑、外部工具适配彼此分层。**
4. **长任务可恢复、可观测、可局部重跑。**
5. **下载、处理、输出互不绑死。**

### 1.3 非目标
本设计不追求：
- 当前就实现 CLI。
- 当前就提供远程 API。
- 当前就支持服务端部署。
- 当前就兼容复杂插件市场。

换句话说：**现在只造一艘桌面船，但龙骨要能承受未来再装一套桅杆。**

---

## 2. 总体架构

```text
┌──────────────────────────────────────────────┐
│                Desktop App Host              │
│  ┌──────────────┐  ┌──────────────────────┐  │
│  │ Desktop UI   │  │ Local App Services   │  │
│  │ React/WPF... │◄►│ Task / Config / Logs │  │
│  └──────────────┘  └──────────┬───────────┘  │
└───────────────────────────────┼──────────────┘
                                │ IPC / in-proc boundary
┌───────────────────────────────▼──────────────┐
│                 Core Engine                  │
│  ┌─────────────────────────────────────────┐ │
│  │ Application Layer                       │ │
│  │ Use Cases / Orchestration / Recovery    │ │
│  └──────────────────┬──────────────────────┘ │
│  ┌──────────────────▼──────────────────────┐ │
│  │ Domain Layer                            │ │
│  │ Task / Stage / Artifact / Pipeline      │ │
│  └──────────────────┬──────────────────────┘ │
│  ┌──────────────────▼──────────────────────┐ │
│  │ Adapter Layer                           │ │
│  │ FFmpeg / ASR / Translator / Downloader  │ │
│  └─────────────────────────────────────────┘ │
└───────────────────────────────┬──────────────┘
                                │
                ┌───────────────▼───────────────┐
                │ Local Filesystem + SQLite DB  │
                │ Assets / Cache / Manifest     │
                └───────────────────────────────┘
```

### 2.1 核心思想
- **Desktop App Host**：当前唯一产品入口，负责交互体验。
- **Core Engine**：真正的产品能力中心，未来 CLI 也只应复用它，而不是复制 Desktop 逻辑。
- **Adapter Layer**：所有外部依赖都关在边界之后，便于未来替换。

---

## 3. 推荐运行形态

### 3.1 MVP 推荐：Desktop UI + 本地 Engine Worker
建议 MVP 采用：
- 一个 Desktop 主进程。
- 一个本地 Engine Worker 进程。
- UI 与 Worker 之间通过本地 IPC 通信。

```text
Desktop UI Process
   │
   ├─ 创建任务
   ├─ 订阅进度
   └─ 展示结果
   │
   ▼
Local Engine Worker Process
   ├─ 调度流水线
   ├─ 调用 FFmpeg / 下载器 / ASR
   ├─ 写 SQLite / manifest
   └─ 汇报状态
```

### 3.2 为什么不是把所有逻辑都塞进 UI 进程
- 视频处理是长任务，不能拖垮界面响应。
- GPU / FFmpeg / 下载器失败时，需要更好的隔离。
- 未来 CLI 可以直接调用同一套 Engine，而不是绕过 UI 重写一遍。
- Worker 进程天然适合做恢复、重启接管与后台执行。

### 3.3 为什么这仍然不是 server-first
- Worker 只在本机运行。
- 不暴露公网服务。
- 不承担多用户、多租户、远程部署能力。
- IPC 是本地实现细节，不是产品形态。

---

## 4. 分层设计

## 4.1 Presentation Layer（Desktop）
职责：
- 页面与交互。
- 用户输入校验。
- 任务进度可视化。
- 错误信息的人类可读转换。

不负责：
- 决定流水线如何执行。
- 拼装 FFmpeg 命令。
- 直接操作任务数据库。
- 直接依赖具体下载器或 ASR 实现。

建议模块：
- `pages/`
- `components/`
- `viewmodels/`
- `ipc-client/`

## 4.2 Application Layer（未来 Desktop / CLI 共用）
职责：
- 处理用例。
- 编排任务生命周期。
- 驱动恢复逻辑。
- 管理配置优先级。
- 对外暴露稳定的应用级接口。

典型用例：
- `CreateTask`
- `StartTask`
- `RetryTask`
- `ResumeTask`
- `CancelTask`
- `GetTaskDetail`
- `ListTasks`
- `ValidateEnvironment`

这层未来就是 CLI 最主要复用的接口层。

## 4.3 Domain Layer（最稳定）
职责：
- 定义产品真正的核心模型与规则。

核心对象：
- `Task`
- `Stage`
- `Artifact`
- `PipelineDefinition`
- `TaskConfigSnapshot`
- `ResumePolicy`
- `ArtifactManifest`

这里不应该出现：
- UI 字段。
- SQLite 细节。
- FFmpeg 命令。
- HTTP 请求。
- Windows 专属逻辑。

## 4.4 Adapter Layer
职责：
- 隔离外部工具与基础设施。

建议适配器：
- `DownloaderAdapter`
  - `LocalFileImporter`
  - `YtDlpDownloader`
  - `CobaltDownloader`
- `MediaAdapter`
  - `FFmpegAdapter`
  - `FFprobeAdapter`
- `AsrAdapter`
  - 首版默认实现。
- `TranslationAdapter`
- `StorageAdapter`
- `TaskRepository`
- `ManifestRepository`

### 4.5 Infrastructure Layer
职责：
- 文件系统。
- SQLite。
- 进程启动。
- IPC。
- 日志。
- 配置文件。

---

## 5. 未来 CLI 的保留方式

### 5.1 不是现在做 CLI，而是现在保留 Host 边界
未来扩展 CLI 时，应新增：

```text
hosts/
  desktop/
  cli/        # 未来新增
core/
  application/
  domain/
  adapters/
```

Desktop 与 CLI 都只能通过 Application Layer 调用能力。

### 5.2 未来 CLI 不应复用什么
- 不应复用 Desktop 的 ViewModel。
- 不应读取 UI 私有状态。
- 不应通过模拟点击或 UI IPC 完成任务。

### 5.3 未来 CLI 应直接复用什么
- 同一份 `CreateTask` / `StartTask` / `ResumeTask` 用例。
- 同一份配置解析。
- 同一份阶段定义。
- 同一份产物目录规范。
- 同一份错误码。

### 5.4 现在必须做出的接口纪律
即使 CLI 暂时不存在，也要把 Application API 设计成非 GUI 专属，例如：

```text
create_task(input, config) -> task_id
start_task(task_id) -> execution_handle
get_task(task_id) -> task_snapshot
list_tasks(filters) -> task_summary[]
retry_task(task_id, from_stage?) -> task_id
resume_task(task_id) -> task_id
cancel_task(task_id) -> void
```

未来 CLI 只是这些能力的另一个薄壳。

---

## 6. 任务与流水线设计

### 6.1 标准流水线

```text
AcquireInput
  ↓
ProbeMedia
  ↓
ExtractAudio
  ↓
TranscribeAudio
  ↓
NormalizeSegments
  ↓
TranslateSegments
  ↓
GenerateSubtitles
  ↓
RenderOrMuxVideo
  ↓
FinalizeArtifacts
```

### 6.2 阶段设计原则
每个阶段必须：
- 有清晰输入。
- 有清晰输出。
- 可单独执行。
- 可判断是否已完成。
- 可声明下游依赖。
- 可产生日志与结构化错误。

### 6.3 阶段状态
- `pending`
- `running`
- `succeeded`
- `failed`
- `skipped`
- `cancelled`
- `invalidated`

### 6.4 任务恢复逻辑
恢复不是“重新开始”，而是：
1. 读取 `manifest.json` 与任务库。
2. 校验每阶段产物是否存在、hash 是否匹配。
3. 找到最近可复用阶段。
4. 从第一个失效阶段继续。

例子：
- 下载成功，ASR 失败 → 从 `TranscribeAudio` 继续。
- 目标语言变化 → `TranslateSegments` 及下游失效。
- 输入视频变化 → 全链路失效。

---

## 7. 数据持久化设计

### 7.1 双轨持久化
建议同时使用：
1. **SQLite**：给应用查询、筛选、历史任务、UI 展示。
2. **manifest.json**：给资产自描述、迁移、恢复、脱离数据库后的可读性。

### 7.2 SQLite 中应保存
- 任务摘要。
- 阶段状态。
- 事件日志索引。
- 用户配置。
- 最近访问。

### 7.3 Manifest 中应保存
- 输入来源。
- 配置快照。
- pipeline 版本。
- 每阶段状态。
- 产物路径与 hash。
- 错误摘要。
- 生成时间。

### 7.4 原则
- SQLite 服务“应用体验”。
- Manifest 服务“资产寿命”。

---

## 8. 文件系统设计

### 8.1 推荐根目录划分

```text
AppData/
  config/
  db/
  cache/
  logs/

User Output Root/
  <asset-slug>/
    source/
    transcripts/
    subtitles/
    video/
    manifest.json
```

### 8.2 临时资产与长期资产分离
- `cache/`：模型缓存、下载中间态、临时音频。
- `output-root/`：用户真正想保留的内容。

### 8.3 这样设计的好处
- 清缓存不会误删成品。
- 迁移输出目录后，资产仍完整。
- 外部媒体工具只需面对稳定产物。

---

## 9. 配置系统设计

### 9.1 配置层级

```text
任务级配置
  > 用户全局配置
  > 系统默认配置
```

### 9.2 配置分类
- 输入配置。
- 下载配置。
- 模型配置。
- 字幕配置。
- 输出配置。
- 执行配置。

### 9.3 配置快照
任务创建时必须保存 `config_snapshot`，原因：
- 保证历史任务可解释。
- 保证重试时可复现。
- 防止用户后来改设置，导致旧任务行为漂移。

---

## 10. 下载能力设计

### 10.1 原则
下载是输入获取能力，不是处理流水线的组成部分。

### 10.2 接口建议

```text
DownloaderAdapter.fetch(source, target_dir) -> AcquiredAsset
```

`AcquiredAsset` 至少包含：
- 本地文件路径。
- 原始来源。
- 下载器类型。
- 标题 / 基础元数据。
- hash。

### 10.3 首版支持
- 本地文件导入。
- `yt-dlp`。
- 自托管 `Cobalt`。

### 10.4 这样做的价值
未来即使新增下载器，也不会触碰：
- ASR。
- 翻译。
- 字幕。
- 输出目录逻辑。

---

## 11. 处理能力设计

### 11.1 ASR
- 通过 `AsrAdapter` 抽象。
- 首版只需一个默认实现。
- 但领域层只认识“转写结果”，不认识具体模型品牌。

### 11.2 翻译
- 通过 `TranslationAdapter` 抽象。
- 首版可仅支持一种实现。
- 中间结果保留，避免翻译变更时重跑 ASR。

### 11.3 字幕
- 字幕生成独立成阶段。
- 不把“字幕文件生成”和“烧录/封装到视频”混为一谈。

### 11.4 视频输出
- 单独由 `RenderOrMuxVideo` 阶段完成。
- 未来支持：
  - 仅输出外挂字幕。
  - mux 内挂字幕。
  - burn-in 烧录字幕。

---

## 12. IPC 与任务事件设计

### 12.1 UI 需要的事件
- 任务创建。
- 阶段开始。
- 阶段进度。
- 阶段成功。
- 阶段失败。
- 任务完成。
- 任务取消。

### 12.2 事件模型建议

```text
TaskEvent
  - task_id
  - event_type
  - stage
  - timestamp
  - progress
  - message
  - payload
```

### 12.3 原则
- UI 订阅事件，而不是轮询内部状态。
- 事件用于展示，不替代持久化事实。
- Worker 重启后，真实状态仍从 SQLite / manifest 恢复。

---

## 13. 错误处理设计

### 13.1 错误分类
- 环境错误：FFmpeg 缺失、GPU 不可用、模型缺失。
- 输入错误：文件损坏、URL 无效。
- 下载错误：站点限制、认证失败。
- 处理错误：ASR 失败、翻译失败、封装失败。
- 输出错误：磁盘不足、目录不可写。

### 13.2 错误对象应包含
- `code`
- `category`
- `stage`
- `human_message`
- `technical_detail`
- `retryable`
- `suggested_action`

### 13.3 体验原则
- UI 展示“人类可读错误”。
- 日志保留“工程可排查细节”。
- 重试策略基于错误类型，而不是一律重跑。

---

## 14. 依赖与技术选型建议

> 这里给的是架构倾向，不是不可更改的铁律。

### 14.1 Core Engine
如果沿用当前项目积累，建议：
- **Python** 继续承载 Core Engine。
- 原因：现有视频处理、AI、FFmpeg 调用链已经在 Python 生态中；未来 CLI 也天然合适。

### 14.2 Desktop Host
可选两条路：

#### 方案 A：Tauri / React + Python Worker
优点：
- UI 现代。
- 包体相对可控。
- 前后端边界清晰。

#### 方案 B：.NET Desktop + Python Worker
优点：
- Windows 原生体验更强。
- 系统集成更顺手。

若团队更熟 Python + Web，优先 A；若团队更熟 Windows 原生开发，优先 B。

### 14.3 进程通信
推荐优先级：
1. 本地 IPC / named pipe。
2. 本地 gRPC。
3. 仅开发阶段可接受 localhost HTTP。

正式产品不建议把“本地 HTTP API”当成核心边界，因为它会悄悄把产品引向 server-first 心智。

### 14.4 本地数据库
- SQLite 足够。
- 不引入重型数据库。

---

## 15. 推荐代码组织

```text
src/
  hosts/
    desktop/
      ui/
      ipc/
      bootstrap/
    cli/                  # 未来预留，不在 MVP 实现

  core/
    application/
      use_cases/
      services/
    domain/
      models/
      pipeline/
      policies/
    adapters/
      downloaders/
      asr/
      translation/
      media/
      repositories/

  infrastructure/
    persistence/
    filesystem/
    logging/
    ipc/
    process/

  tests/
    unit/
    integration/
    fixtures/
```

### 15.1 当前旧仓库迁移建议
现有代码已出现一些有价值的雏形：
- `pipeline/`
- `stages/`
- `config`
- `context`

但未来应避免继续沿着“脚本式流水线”堆叠，建议演进为：
- `pipeline/stages/*` → Domain + Application 可识别的阶段对象。
- `config.py` → 显式区分默认配置、用户配置、任务快照。
- `context.py` → 替换为更稳定的 `TaskContext / ArtifactManifest`。
- 下载、翻译、ASR 逐步从阶段内部抽为 adapters。

---

## 16. MVP 的架构交付物

MVP 不只是“有功能”，还应交付这些骨架：

### 16.1 必须落地
- Core Engine 包。
- Desktop Host。
- 本地 Worker。
- Application API。
- Task / Stage / Artifact 领域模型。
- SQLite 存储。
- Manifest 规范。
- 下载器适配接口。
- ASR / 翻译 / FFmpeg 适配接口。
- 阶段级恢复。
- 结构化错误与事件。

### 16.2 可以暂缓
- 真正的 CLI Host。
- 插件市场。
- 多模型自动调度。
- 高级编辑器。
- 远程访问能力。

---

## 17. 关键架构决策

### ADR-001：MVP 只做 Desktop，但核心能力脱离 UI
**原因**：避免未来 CLI 出现第二套逻辑。

### ADR-002：采用本地 Worker，而非所有逻辑塞进 UI 进程
**原因**：长任务、失败隔离、恢复能力。

### ADR-003：采用 SQLite + manifest 双轨持久化
**原因**：同时服务应用体验与长期资产寿命。

### ADR-004：下载器、ASR、翻译器、媒体处理器全部适配器化
**原因**：外部依赖最容易变，核心域最不该跟着变。

### ADR-005：不提供媒体中心集成层
**原因**：产品边界必须守住。

---

## 18. 最终结论

MVP 的正确形状不是：

```text
Desktop App = UI + 一坨视频处理代码
```

而是：

```text
Desktop App = 当前唯一 Host
Core Engine = 真正可持续演进的产品内核
CLI = 未来新增的另一个 Host
```

这样首版不会为了“未来可能的 CLI”承担双端开发成本，却已经在架构上拒绝了未来重写。
