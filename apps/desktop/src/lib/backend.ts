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

function previewTask(): TaskSummary {
  return {
    id: "browser-preview-study",
    title: "Echo Vidstack Preview",
    status: "succeeded",
    stageLabel: "finalize_video",
    detail: "浏览器预览演示任务",
    assetDir: "preview://echo",
    progress: 1,
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
  };
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
    return shouldShowStudyPreview() ? [previewTask()] : [];
  }
}

export const isTauriRuntime = tauriIsTauri();
export const backend: DesktopBackend = isTauriRuntime ? new TauriBackend() : new BrowserPreviewBackend();
