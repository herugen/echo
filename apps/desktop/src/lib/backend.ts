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
00:00:03,187 --> 00:00:27,892
Now I'm going to show what needs to be done on the cloud side. So this is the IoT Core. So the IoT Core has the certificate authority. So the certificate authority, basically you would add that public certificate that was created. So when you create a wiki. So that public certificate needs to be uploaded.

2
00:00:28,415 --> 00:00:52,343
to the IoT Core. So I'm just uploading the IoT certificate and I'm also copying the device sign. So this device sign will be done by us once we have the API key. So all you need to do on your side is just to upload that public certificate and that's it. We will create and inject the devices for you.

3
00:00:52,681 --> 00:01:14,686
So this is uploading the public certificate and register. So now under your certificate authority, you will have a new certificate that you generated through the app for the YubiKey. So this will complete everything you need to do on your side.

4
00:01:15,074 --> 00:01:41,450
For our side, what we will do, right now I'm showing you why, but this will be automated. Basically, I'm showing you how we are registering device. So I'm selecting the public key that was used to sign the devices. And then that signed certificate the device has, so that I've registered that with IoT Core. So now IoT Core recognizes this certificate.
`;

const previewTranslatedSrt = `1
00:00:03,187 --> 00:00:27,892
现在我来展示需要在云端完成的操作。这是IoT Core。IoT Core拥有证书颁发机构。基本上，你需要上传之前创建的公共证书。当你创建一个wiki时，这个公共证书需要被上传。

2
00:00:28,415 --> 00:00:52,343
到IoT Core。我正在上传IoT证书，同时也在复制设备签名。一旦我们有了API密钥，这个设备签名将由我们完成。你只需要上传那个公共证书就可以了。我们会为你创建并注入设备。

3
00:00:52,681 --> 00:01:14,686
这是上传公共证书并注册。现在，在你的证书颁发机构下，你将有一个通过YubiKey应用生成的新证书。这将完成你这边需要做的所有操作。

4
00:01:15,074 --> 00:01:41,450
至于我们这边，现在我在展示原因，但这将是自动化的。基本上，我在展示我们如何注册设备。我选择用于签署设备的公钥。然后设备拥有的那个签名证书，我已经在IoT Core中注册了。现在IoT Core识别这个证书。
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
        title: "IoT Core 长字幕学习片段",
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
