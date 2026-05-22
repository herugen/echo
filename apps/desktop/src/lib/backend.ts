import { invoke, isTauri as tauriIsTauri } from "@tauri-apps/api/core";
import { open } from "@tauri-apps/plugin-dialog";
import type { AppSettings, TaskSummary } from "../types";

export interface DesktopBackend {
  getSettings(): Promise<AppSettings>;
  chooseOutputDir(): Promise<AppSettings | null>;
  saveTranslationSettings(settings: Pick<AppSettings, "deepseekBaseUrl" | "deepseekApiKey">): Promise<AppSettings>;
  createLocalVideoTask(): Promise<TaskSummary | null>;
  createUrlVideoTask(url: string): Promise<TaskSummary>;
  startTask(taskId: string): Promise<void>;
  retryTask(taskId: string): Promise<void>;
  pauseTask(taskId: string): Promise<TaskSummary>;
  deleteTask(taskId: string): Promise<void>;
  openPath(path: string): Promise<void>;
  readTextFile(path: string): Promise<string>;
  listTasks(): Promise<TaskSummary[]>;
}

const PREVIEW_VIDEO_URL = "https://interactive-examples.mdn.mozilla.net/media/cc0-videos/flower.mp4";
const PREVIEW_SOURCE_SRT = `1
00:00:00,000 --> 00:00:01,400
Welcome to Echo.

2
00:00:01,400 --> 00:00:02,700
This player is powered by Vidstack.

3
00:00:02,700 --> 00:00:04,000
Jump sentence by sentence while the video keeps context.

4
00:00:04,000 --> 00:00:05,300
Loop one line until the rhythm feels natural.
`;
const PREVIEW_TRANSLATED_SRT = `1
00:00:00,000 --> 00:00:01,400
欢迎来到 Echo。

2
00:00:01,400 --> 00:00:02,700
这个播放器现在由 Vidstack 驱动。

3
00:00:02,700 --> 00:00:04,000
你可以按句跳转，同时保留视频上下文。

4
00:00:04,000 --> 00:00:05,300
单句循环，直到节奏变得自然。
`;
const PREVIEW_BILINGUAL_SRT = `1
00:00:00,000 --> 00:00:01,400
Welcome to Echo.
欢迎来到 Echo。

2
00:00:01,400 --> 00:00:02,700
This player is powered by Vidstack.
这个播放器现在由 Vidstack 驱动。

3
00:00:02,700 --> 00:00:04,000
Jump sentence by sentence while the video keeps context.
你可以按句跳转，同时保留视频上下文。

4
00:00:04,000 --> 00:00:05,300
Loop one line until the rhythm feels natural.
单句循环，直到节奏变得自然。
`;

function shouldShowStudyPreview(): boolean {
  return typeof window !== "undefined" && new URLSearchParams(window.location.search).get("studyPreview") === "1";
}

function previewTask(overrides: Partial<TaskSummary> = {}): TaskSummary {
  const id = overrides.id ?? "browser-preview-study";
  return {
    id,
    title: "Echo Vidstack Preview",
    status: "succeeded",
    stageLabel: "finalize_video",
    detail: "浏览器预览演示任务",
    assetDir: `preview://${id}`,
    progress: 1,
    sourceLabel: "Echo Preview",
    description: "逐句播放、双语字幕、短句学习卡片都已准备好。",
    durationSeconds: 5,
    addedLabel: "刚刚",
    resolutionLabel: "1080p",
    thumbnailKind: "studio",
    stages: [
      {
        name: "acquire_input",
        status: "succeeded",
        detail: "Preview video",
        artifacts: [PREVIEW_VIDEO_URL],
      },
      {
        name: "generate_source_subtitles",
        status: "succeeded",
        artifacts: ["preview://source.srt"],
      },
      {
        name: "generate_translated_subtitles",
        status: "succeeded",
        artifacts: ["preview://translated.srt"],
      },
      {
        name: "generate_bilingual_subtitles",
        status: "succeeded",
        artifacts: ["preview://bilingual.srt"],
      },
      {
        name: "finalize_video",
        status: "succeeded",
        artifacts: [],
      },
    ],
    ...overrides,
  };
}

function previewLibrary(): TaskSummary[] {
  return [
    previewTask({
      id: "preview-nba-highlights",
      title: "4 CAVALIERS at 3 KNICKS FULL GAME 1 HIGHLIGHTS",
      sourceLabel: "NBA",
      description: "东部季后赛焦点战，已生成短句双语字幕和本地播放资产。",
      durationSeconds: 1051,
      addedLabel: "5天前",
      resolutionLabel: "1080p",
      thumbnailKind: "sports",
    }),
    previewTask({
      id: "preview-gtc-keynote",
      title: "英伟达 NVIDIA GTC 2024 主题演讲",
      sourceLabel: "NVIDIA 官方频道",
      description: "AI 与计算平台更新摘要，适合逐句复习术语表达。",
      durationSeconds: 5652,
      addedLabel: "2天前",
      resolutionLabel: "1080p",
      thumbnailKind: "studio",
    }),
    previewTask({
      id: "preview-ice-road",
      title: "冰岛环岛公路旅行完整记录",
      sourceLabel: "旅行者小林",
      description: "10 天游记，字幕已切分为短句，适合影像听力输入。",
      durationSeconds: 1427,
      addedLabel: "3天前",
      resolutionLabel: "4K",
      thumbnailKind: "road",
    }),
    previewTask({
      id: "preview-coffee-bgm",
      title: "雨天咖啡馆爵士乐 - 放松与专注",
      sourceLabel: "Cafe Music BGM channel",
      description: "工作或学习背景音，本地缓存后可离线播放。",
      durationSeconds: 10934,
      addedLabel: "1周前",
      resolutionLabel: "1080p",
      thumbnailKind: "coffee",
    }),
    previewTask({
      id: "preview-space",
      title: "国际空间站：下一站火星？",
      sourceLabel: "The Explorers",
      description: "航天科普片段，适合保存到本地媒体库长期复看。",
      durationSeconds: 2718,
      addedLabel: "1周前",
      resolutionLabel: "1080p",
      thumbnailKind: "space",
    }),
    previewTask({
      id: "preview-mit-linear",
      title: "线性代数的本质（MIT 18.06）",
      sourceLabel: "MIT OpenCourseWare",
      description: "课程讲解向量空间与线性变换，中文字幕已生成。",
      durationSeconds: 1716,
      addedLabel: "2周前",
      resolutionLabel: "720p",
      thumbnailKind: "lecture",
    }),
    previewTask({
      id: "preview-tokyo-night",
      title: "东京夜游 4K - 新宿、涩谷、银座",
      sourceLabel: "Vivid Japan",
      description: "城市夜景和街头环境声，适合沉浸式观看。",
      durationSeconds: 4122,
      addedLabel: "2周前",
      resolutionLabel: "4K",
      thumbnailKind: "city",
    }),
    previewTask({
      id: "preview-study-bgm",
      title: "学习专注 | 白噪音 + 钢琴曲 2 小时",
      sourceLabel: "自习室 BGM",
      description: "提升专注力的轻音乐，适合离线循环播放。",
      durationSeconds: 7200,
      addedLabel: "3周前",
      resolutionLabel: "1080p",
      thumbnailKind: "focus",
    }),
    {
      ...previewTask({
        id: "preview-processing-wwdc",
        title: "Apple WWDC 2024 - Keynote",
        sourceLabel: "Apple",
        description: "正在转写和生成双语字幕。",
        durationSeconds: 5400,
        addedLabel: "下载中",
        resolutionLabel: "1080p",
        thumbnailKind: "desktop",
      }),
      status: "running",
      stageLabel: "translate_segments",
      progress: 0.73,
      detail: "处理中 · 剩余约 3 分钟",
    },
    {
      ...previewTask({
        id: "preview-processing-deepmind",
        title: "DeepMind 最新研究：AI 推理的未来",
        sourceLabel: "DeepMind",
        description: "正在获取视频和元数据。",
        durationSeconds: 3180,
        addedLabel: "下载中",
        resolutionLabel: "1080p",
        thumbnailKind: "studio",
      }),
      status: "running",
      stageLabel: "acquire_input",
      progress: 0.42,
      detail: "下载中 · 12.4 MB/s · 剩余 5 分钟",
    },
  ];
}

class TauriBackend implements DesktopBackend {
  getSettings(): Promise<AppSettings> {
    return invoke<AppSettings>("get_settings");
  }

  async chooseOutputDir(): Promise<AppSettings | null> {
    const selected = await open({ multiple: false, directory: true });
    if (!selected || Array.isArray(selected)) {
      return null;
    }
    return invoke<AppSettings>("set_output_dir", { outputDir: selected });
  }

  saveTranslationSettings(settings: Pick<AppSettings, "deepseekBaseUrl" | "deepseekApiKey">): Promise<AppSettings> {
    return invoke<AppSettings>("set_translation_settings", settings);
  }

  async createLocalVideoTask(): Promise<TaskSummary | null> {
    const selected = await open({
      multiple: false,
      directory: false,
      filters: [
        {
          name: "Video",
          extensions: ["mp4", "mkv", "mov", "avi", "webm"],
        },
      ],
    });

    if (!selected || Array.isArray(selected)) {
      return null;
    }

    return invoke<TaskSummary>("create_local_video_task", { sourcePath: selected });
  }

  createUrlVideoTask(url: string): Promise<TaskSummary> {
    return invoke<TaskSummary>("create_url_video_task", { url });
  }

  startTask(taskId: string): Promise<void> {
    return invoke<void>("start_task", { taskId });
  }

  retryTask(taskId: string): Promise<void> {
    return invoke<void>("retry_task", { taskId });
  }

  pauseTask(taskId: string): Promise<TaskSummary> {
    return invoke<TaskSummary>("pause_task", { taskId });
  }

  deleteTask(taskId: string): Promise<void> {
    return invoke<void>("delete_task", { taskId });
  }

  openPath(path: string): Promise<void> {
    return invoke<void>("open_path", { targetPath: path });
  }

  readTextFile(path: string): Promise<string> {
    return invoke<string>("read_text_file", { path });
  }

  listTasks(): Promise<TaskSummary[]> {
    return invoke<TaskSummary[]>("list_tasks");
  }
}

class BrowserPreviewBackend implements DesktopBackend {
  async getSettings(): Promise<AppSettings> {
    return {
      outputDir: "桌面应用中可配置",
      translatorBackend: "deepseek",
      deepseekBaseUrl: "https://api.deepseek.com/v1",
      deepseekApiKey: "",
    };
  }

  async chooseOutputDir(): Promise<AppSettings | null> {
    throw new Error("请在桌面应用中选择输出目录。");
  }

  async saveTranslationSettings(): Promise<AppSettings> {
    throw new Error("请在桌面应用中保存翻译设置。");
  }

  async createLocalVideoTask(): Promise<TaskSummary | null> {
    throw new Error("请在桌面应用中导入真实视频。");
  }

  async createUrlVideoTask(): Promise<TaskSummary> {
    throw new Error("请在桌面应用中处理真实 URL。");
  }

  async startTask(): Promise<void> {
    throw new Error("请在桌面应用中运行任务。");
  }

  async retryTask(): Promise<void> {
    throw new Error("请在桌面应用中重试任务。");
  }

  async pauseTask(): Promise<TaskSummary> {
    throw new Error("请在桌面应用中暂停任务。");
  }

  async deleteTask(): Promise<void> {
    throw new Error("请在桌面应用中删除任务。");
  }

  async openPath(): Promise<void> {
    throw new Error("请在桌面应用中打开本地路径。");
  }

  async readTextFile(path: string): Promise<string> {
    if (path === "preview://source.srt") {
      return PREVIEW_SOURCE_SRT;
    }
    if (path === "preview://translated.srt") {
      return PREVIEW_TRANSLATED_SRT;
    }
    if (path === "preview://bilingual.srt") {
      return PREVIEW_BILINGUAL_SRT;
    }
    throw new Error("请在桌面应用中读取真实字幕。");
  }

  async listTasks(): Promise<TaskSummary[]> {
    return shouldShowStudyPreview() ? previewLibrary() : [];
  }
}

export const isTauriRuntime = tauriIsTauri();
export const backend: DesktopBackend = isTauriRuntime ? new TauriBackend() : new BrowserPreviewBackend();
