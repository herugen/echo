import { invoke } from "@tauri-apps/api/core";
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

  async listTasks(): Promise<TaskSummary[]> {
    return [];
  }
}

const isTauri = typeof window !== "undefined" && "__TAURI_INTERNALS__" in window;
export const backend: DesktopBackend = isTauri ? new TauriBackend() : new BrowserPreviewBackend();
