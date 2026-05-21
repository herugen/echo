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

const previewSourceSrt = `1
00:00:00,000 --> 00:00:01,300
Speaking of desserts, we are going to dig in.

2
00:00:01,300 --> 00:00:02,600
Which means to begin eating.

3
00:00:02,600 --> 00:00:03,800
Oh, yeeeeeeah.

4
00:00:03,800 --> 00:00:05,000
This is the kind of sentence you can replay until it feels natural.
`;

const previewTranslatedSrt = `1
00:00:00,000 --> 00:00:01,300
说到甜点，我们要开动了。

2
00:00:01,300 --> 00:00:02,600
dig in 的意思就是开始吃。

3
00:00:02,600 --> 00:00:03,800
哦，太对了。

4
00:00:03,800 --> 00:00:05,000
这种句子就适合反复听到顺嘴。
`;

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
    if (path.includes("translated")) {
      return previewTranslatedSrt;
    }
    return previewSourceSrt;
  }

  async listTasks(): Promise<TaskSummary[]> {
    return [
      {
        id: "browser-preview-study",
        title: "咖啡馆英语学习片段",
        status: "succeeded",
        stageLabel: "处理已完成",
        detail: "浏览器预览数据",
        outputDir: "browser-preview",
        assetDir: "browser-preview",
        progress: 1,
        stages: [
          {
            name: "acquire_input",
            status: "succeeded",
            detail: "Preview video",
            artifacts: ["https://interactive-examples.mdn.mozilla.net/media/cc0-videos/flower.mp4"],
          },
          {
            name: "generate_source_subtitles",
            status: "succeeded",
            detail: "Preview source subtitles",
            artifacts: ["preview://source.srt"],
          },
          {
            name: "generate_translated_subtitles",
            status: "succeeded",
            detail: "Preview translated subtitles",
            artifacts: ["preview://translated.zh-CN.srt"],
          },
          {
            name: "finalize_video",
            status: "succeeded",
            detail: "Preview exported assets",
            artifacts: [],
          },
        ],
      },
    ];
  }
}

export const isTauriRuntime = tauriIsTauri();
export const backend: DesktopBackend = isTauriRuntime ? new TauriBackend() : new BrowserPreviewBackend();
