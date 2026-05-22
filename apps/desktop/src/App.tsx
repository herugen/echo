import { useEffect, useMemo, useRef, useState } from "react";
import { listen } from "@tauri-apps/api/event";
import "./App.css";
import { StudySession } from "./StudySession";
import { backend, isTauriRuntime } from "./lib/backend";
import type { AppSettings, TaskSummary } from "./types";

const stageLabels: Record<string, string> = {
  acquire_input: "获取视频",
  probe_media: "读取媒体信息",
  extract_audio: "提取音频",
  transcribe_audio: "语音转写",
  generate_source_subtitles: "生成原文字幕",
  translate_segments: "翻译字幕",
  generate_translated_subtitles: "生成译文字幕",
  generate_bilingual_subtitles: "生成双语字幕",
  finalize_video: "导出结果",
};

const statusLabels: Record<string, string> = {
  draft: "等待中",
  running: "运行中",
  failed: "失败",
  succeeded: "完成",
  cancelled: "已取消",
  paused: "已暂停",
  pending: "等待",
  skipped: "复用",
};

type LibraryFilter = "all" | "recent" | "bilingual" | "local";
type AppNav = "home" | "library" | "processing" | "downloads";
type AppIconName =
  | "arrowLeft"
  | "clock"
  | "copy"
  | "download"
  | "file"
  | "folder"
  | "grid"
  | "home"
  | "library"
  | "link"
  | "list"
  | "more"
  | "pause"
  | "play"
  | "plus"
  | "retry"
  | "search"
  | "settings"
  | "subtitles"
  | "trash";

interface VideoCardModel {
  task: TaskSummary;
  title: string;
  channel: string;
  description: string;
  duration: string;
  added: string;
  resolution: string;
  subtitleLabel: string;
  thumbnailKind: string;
}

const libraryFilters: Array<{ id: LibraryFilter; label: string }> = [
  { id: "all", label: "全部" },
  { id: "recent", label: "最近添加" },
  { id: "bilingual", label: "中英双语" },
  { id: "local", label: "本地文件" },
];

function labelStage(name: string): string {
  return stageLabels[name] ?? name;
}

function labelStatus(status: string): string {
  return statusLabels[status] ?? status;
}

function taskStatusSummary(task: TaskSummary): string {
  if (task.status === "running") {
    return labelStage(task.stageLabel) || "运行中";
  }
  if (task.status === "failed") {
    return `${labelStage(task.stageLabel) || "处理"}失败`;
  }
  return labelStatus(task.status);
}

function failedDetail(task: TaskSummary): string {
  return task.stages?.find((stage) => stage.status === "failed")?.detail ?? task.detail;
}

function outputArtifacts(task: TaskSummary): string[] {
  return task.stages?.find((stage) => stage.name === "finalize_video")?.artifacts ?? [];
}

function exportTarget(task: TaskSummary): string {
  return outputArtifacts(task)[0] ?? task.outputDir ?? task.assetDir;
}

function isTextField(target: EventTarget | null): target is HTMLInputElement | HTMLTextAreaElement {
  return target instanceof HTMLInputElement || target instanceof HTMLTextAreaElement;
}

function canDeleteTask(task: TaskSummary): boolean {
  return task.status !== "running";
}

function hasStageArtifact(task: TaskSummary, stageName: string): boolean {
  return !!task.stages?.find((stage) => stage.name === stageName)?.artifacts?.length;
}

function formatDuration(seconds?: number): string {
  if (!seconds || !Number.isFinite(seconds) || seconds <= 0) {
    return "--:--";
  }
  const rounded = Math.round(seconds);
  const hours = Math.floor(rounded / 3600);
  const minutes = Math.floor((rounded % 3600) / 60);
  const secs = rounded % 60;
  if (hours > 0) {
    return `${hours}:${String(minutes).padStart(2, "0")}:${String(secs).padStart(2, "0")}`;
  }
  return `${minutes}:${String(secs).padStart(2, "0")}`;
}

function describeTask(task: TaskSummary): string {
  if (task.description) {
    return task.description;
  }
  if (task.status === "succeeded") {
    return "已生成本地视频、字幕和双语学习轨，可直接播放复习。";
  }
  if (task.status === "failed") {
    return failedDetail(task);
  }
  return task.detail || "本地处理任务正在准备。";
}

function buildVideoCard(task: TaskSummary, index: number): VideoCardModel {
  const subtitleLabel = hasStageArtifact(task, "generate_bilingual_subtitles")
    ? "中英双语"
    : hasStageArtifact(task, "generate_translated_subtitles")
      ? "中文字幕"
      : "字幕";
  const thumbnailThemes = ["studio", "road", "sports", "coffee", "space", "lecture", "city", "food", "desktop", "focus"];
  return {
    task,
    title: task.title || "未命名视频",
    channel: task.sourceLabel ?? (task.assetDir.startsWith("preview://") ? "Echo Preview" : "本地媒体"),
    description: describeTask(task),
    duration: task.durationLabel ?? formatDuration(task.durationSeconds),
    added: task.addedLabel ?? "本地任务",
    resolution: task.resolutionLabel ?? "本地",
    subtitleLabel,
    thumbnailKind: task.thumbnailKind ?? thumbnailThemes[index % thumbnailThemes.length],
  };
}

function AppIcon({ name }: { name: AppIconName }) {
  const paths: Record<AppIconName, string[]> = {
    arrowLeft: ["M19 12H5", "m12 5-7 7 7 7"],
    clock: ["M12 7v5l3 2", "M21 12a9 9 0 1 1-18 0 9 9 0 0 1 18 0Z"],
    copy: ["M8 8h10v12H8Z", "M6 16H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h9a2 2 0 0 1 2 2v1"],
    download: ["M12 3v11", "m7 10 5 5 5-5", "M5 21h14"],
    file: ["M14 3H7a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h10a2 2 0 0 0 2-2V8Z", "M14 3v5h5"],
    folder: ["M3 7a2 2 0 0 1 2-2h4l2 2h8a2 2 0 0 1 2 2v8a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2Z"],
    grid: ["M4 4h6v6H4Z", "M14 4h6v6h-6Z", "M4 14h6v6H4Z", "M14 14h6v6h-6Z"],
    home: ["M3 11 12 4l9 7", "M5 10v10h5v-6h4v6h5V10"],
    library: ["M5 4h14v16H5Z", "M9 8h6", "M9 12h6", "M9 16h4"],
    link: ["M10 13a5 5 0 0 0 7.1 0l1.4-1.4a5 5 0 0 0-7.1-7.1l-.8.8", "M14 11a5 5 0 0 0-7.1 0l-1.4 1.4a5 5 0 0 0 7.1 7.1l.8-.8"],
    list: ["M8 6h13", "M8 12h13", "M8 18h13", "M3 6h.01", "M3 12h.01", "M3 18h.01"],
    more: ["M12 6h.01", "M12 12h.01", "M12 18h.01"],
    pause: ["M8 5v14", "M16 5v14"],
    play: ["m8 5 11 7-11 7Z"],
    plus: ["M12 5v14", "M5 12h14"],
    retry: ["M4 4v6h6", "M20 20v-6h-6", "M5 15a7 7 0 0 0 12 3l3-4", "M19 9A7 7 0 0 0 7 6l-3 4"],
    search: ["M11 19a8 8 0 1 1 0-16 8 8 0 0 1 0 16Z", "m21 21-4.3-4.3"],
    settings: ["M12 15.5a3.5 3.5 0 1 0 0-7 3.5 3.5 0 0 0 0 7Z", "M19 12a7 7 0 0 0-.1-1.2l2-1.5-2-3.4-2.4 1a7 7 0 0 0-2-1.2L14.2 3h-4.4l-.3 2.7a7 7 0 0 0-2 1.2l-2.4-1-2 3.4 2 1.5A7 7 0 0 0 5 12c0 .4 0 .8.1 1.2l-2 1.5 2 3.4 2.4-1a7 7 0 0 0 2 1.2l.3 2.7h4.4l.3-2.7a7 7 0 0 0 2-1.2l2.4 1 2-3.4-2-1.5c.1-.4.1-.8.1-1.2Z"],
    subtitles: ["M4 6h16v12H4Z", "M8 11h3", "M13 11h3", "M8 15h8"],
    trash: ["M4 7h16", "M10 11v6", "M14 11v6", "M6 7l1 14h10l1-14", "M9 7V4h6v3"],
  };

  return (
    <svg className="button-icon" viewBox="0 0 24 24" aria-hidden="true">
      {paths[name].map((path) => (
        <path d={path} key={path} />
      ))}
    </svg>
  );
}

function App() {
  const [tasks, setTasks] = useState<TaskSummary[]>([]);
  const [settings, setSettings] = useState<AppSettings | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [videoUrl, setVideoUrl] = useState("");
  const [studyTaskId, setStudyTaskId] = useState<string | null>(null);
  const [libraryFilter, setLibraryFilter] = useState<LibraryFilter>("all");
  const [activeNav, setActiveNav] = useState<AppNav>("home");
  const [importOpen, setImportOpen] = useState(false);
  const [copiedPath, setCopiedPath] = useState<string | null>(null);
  const [settingsOpen, setSettingsOpen] = useState(false);
  const startingTasks = useRef<Set<string>>(new Set());
  const autoStartQueue = useRef<Set<string>>(new Set());

  const studyTask = useMemo(
    () => tasks.find((task) => task.id === studyTaskId && task.status === "succeeded") ?? null,
    [studyTaskId, tasks],
  );
  const completedTasks = useMemo(() => tasks.filter((task) => task.status === "succeeded"), [tasks]);
  const processingTasks = useMemo(() => tasks.filter((task) => task.status !== "succeeded"), [tasks]);
  const videoCards = useMemo(() => completedTasks.map(buildVideoCard), [completedTasks]);
  const visibleCards = useMemo(() => {
    if (libraryFilter === "bilingual") {
      return videoCards.filter((card) => card.subtitleLabel.includes("双语"));
    }
    if (libraryFilter === "local") {
      return videoCards.filter((card) => card.channel === "本地媒体" || card.task.assetDir !== "preview://echo");
    }
    return videoCards;
  }, [libraryFilter, videoCards]);
  const processingCount = processingTasks.length;

  useEffect(() => {
    const handleKeyboardClipboard = async (event: KeyboardEvent) => {
      if ((!event.ctrlKey && !event.metaKey) || event.altKey || isTextField(event.target)) {
        return;
      }
      if (event.key.toLowerCase() !== "c") {
        return;
      }

      const selectedText = window.getSelection()?.toString();
      if (selectedText) {
        event.preventDefault();
        await navigator.clipboard?.writeText(selectedText);
      }
    };

    window.addEventListener("keydown", handleKeyboardClipboard);
    return () => window.removeEventListener("keydown", handleKeyboardClipboard);
  }, []);

  useEffect(() => {
    Promise.all([backend.getSettings(), backend.listTasks()])
      .then(([nextSettings, nextTasks]) => {
        setError(null);
        setSettings(nextSettings);
        setTasks(nextTasks);
      })
      .catch((cause) => {
        const message = cause instanceof Error ? cause.message : String(cause || "初始化失败");
        setError(message);
      });

    if (!isTauriRuntime) {
      return;
    }

    const unlistenUpdates = listen<TaskSummary>("task_updated", (event) => {
      mergeTask(event.payload);
    });
    const unlistenCompleted = listen<TaskSummary>("task_completed", (event) => {
      mergeTask(event.payload);
    });
    const unlistenFailed = listen<TaskSummary>("task_failed", (event) => {
      mergeTask(event.payload);
    });
    const unlistenErrors = listen<string>("task-error", (event) => {
      setError(event.payload);
    });
    const unlistenOpenSettings = listen("open_settings", () => {
      setSettingsOpen(true);
    });

    return () => {
      void unlistenUpdates.then((unlisten) => unlisten());
      void unlistenCompleted.then((unlisten) => unlisten());
      void unlistenFailed.then((unlisten) => unlisten());
      void unlistenErrors.then((unlisten) => unlisten());
      void unlistenOpenSettings.then((unlisten) => unlisten());
    };
  }, []);

  useEffect(() => {
    if (tasks.some((task) => task.status === "running")) {
      return;
    }
    const nextTask = tasks.find((task) => task.status === "draft" && autoStartQueue.current.has(task.id) && !startingTasks.current.has(task.id));
    if (!nextTask) {
      return;
    }
    startingTasks.current.add(nextTask.id);
    backend.startTask(nextTask.id).catch((cause) => {
      setError(cause instanceof Error ? cause.message : "启动队列任务失败");
      startingTasks.current.delete(nextTask.id);
      autoStartQueue.current.delete(nextTask.id);
    });
  }, [tasks]);

  function mergeTask(nextTask: TaskSummary) {
    if (nextTask.status !== "draft") {
      startingTasks.current.delete(nextTask.id);
      autoStartQueue.current.delete(nextTask.id);
    }
    setTasks((current) => {
      const existing = current.findIndex((task) => task.id === nextTask.id);
      if (existing === -1) {
        return [nextTask, ...current];
      }
      return current.map((task) => (task.id === nextTask.id ? nextTask : task));
    });
  }

  async function handleRetry(taskId: string) {
    setError(null);
    try {
      await backend.retryTask(taskId);
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : "重试失败");
    }
  }

  async function handleStartTask(taskId: string) {
    setError(null);
    try {
      startingTasks.current.add(taskId);
      await backend.startTask(taskId);
      setActiveNav("processing");
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : "启动任务失败");
      startingTasks.current.delete(taskId);
    }
  }

  async function handlePauseTask(taskId: string) {
    setError(null);
    try {
      const task = await backend.pauseTask(taskId);
      mergeTask(task);
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : "暂停任务失败");
    }
  }

  async function handleDeleteTask(taskId: string) {
    setError(null);
    try {
      await backend.deleteTask(taskId);
      setTasks((current) => current.filter((task) => task.id !== taskId));
      setStudyTaskId((current) => (current === taskId ? null : current));
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : "删除任务失败");
    }
  }

  async function handleSaveTranslationSettings() {
    if (!settings) return;
    setError(null);
    try {
      const nextSettings = await backend.saveTranslationSettings({
        deepseekBaseUrl: settings.deepseekBaseUrl,
        deepseekApiKey: settings.deepseekApiKey,
      });
      setSettings(nextSettings);
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : "保存翻译设置失败");
    }
  }

  async function handleChooseOutputDir() {
    setError(null);
    try {
      const nextSettings = await backend.chooseOutputDir();
      if (nextSettings) {
        setSettings(nextSettings);
      }
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : "设置输出目录失败");
    }
  }

  async function handleImport() {
    setBusy(true);
    setError(null);
    try {
      const task = await backend.createLocalVideoTask();
      if (task) {
        autoStartQueue.current.add(task.id);
        mergeTask(task);
        setActiveNav("processing");
      }
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : "导入失败");
    } finally {
      setBusy(false);
    }
  }

  async function handleUrlImport() {
    const url = videoUrl.trim();
    if (!url) {
      setError("先粘贴一个在线视频链接。");
      return;
    }
    setBusy(true);
    setError(null);
    try {
      const task = await backend.createUrlVideoTask(url);
      autoStartQueue.current.add(task.id);
      mergeTask(task);
      setVideoUrl("");
      setImportOpen(false);
      setActiveNav("downloads");
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : "创建 URL 任务失败");
    } finally {
      setBusy(false);
    }
  }

  async function handleOpenPath(path: string) {
    setError(null);
    try {
      await backend.openPath(path);
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : "打开路径失败");
    }
  }

  async function handleCopyPath(path: string) {
    setError(null);
    try {
      await navigator.clipboard.writeText(path);
      setCopiedPath(path);
      window.setTimeout(() => setCopiedPath((current) => (current === path ? null : current)), 1400);
    } catch {
      setError("复制路径失败");
    }
  }

  return (
    <main className="app-shell video-hub-shell">
      <aside className="hub-sidebar" aria-label="主导航">
        <div className="brand-lockup hub-brand">
          <div className="brand-mark" aria-hidden="true">E</div>
          <div>
            <strong>Echo</strong>
            <span>本地视频中心</span>
          </div>
        </div>

        <nav className="hub-nav">
          {[
            { id: "home" as const, label: "首页", icon: "home" as const },
            { id: "library" as const, label: "媒体库", icon: "library" as const },
            { id: "processing" as const, label: "处理中", icon: "clock" as const, count: processingCount },
            { id: "downloads" as const, label: "下载中", icon: "download" as const, count: processingTasks.filter((task) => task.stageLabel === "acquire_input").length },
          ].map((item) => (
            <button
              className={activeNav === item.id ? "active" : ""}
              key={item.id}
              onClick={() => setActiveNav(item.id)}
              type="button"
            >
              <AppIcon name={item.icon} />
              {item.label}
              {item.count ? <span>{item.count}</span> : null}
            </button>
          ))}
        </nav>

        <div className="playlist-block">
          <div className="sidebar-section-title">
            <span>播放列表</span>
            <button type="button" aria-label="新建播放列表">
              <AppIcon name="plus" />
            </button>
          </div>
          <button type="button"><AppIcon name="clock" />稍后观看<span>{completedTasks.length}</span></button>
          <button type="button"><AppIcon name="subtitles" />双语复习<span>{videoCards.filter((card) => card.subtitleLabel.includes("双语")).length}</span></button>
        </div>

        <div className="storage-card">
          <span>本地存储</span>
          <strong>Echo Library</strong>
          <div className="storage-track"><div /></div>
          <button className="text-button" onClick={handleChooseOutputDir}>存储管理</button>
        </div>
      </aside>

      <section className="hub-main">
        <header className="hub-topbar">
          <label className="search-field">
            <AppIcon name="search" />
            <input placeholder="搜索本地视频（标题、来源、简介、字幕内容）" />
            <kbd>/</kbd>
          </label>
          <div className="topbar-actions">
            <button className="secondary" onClick={handleImport} disabled={busy}>
              <AppIcon name="plus" />
              导入视频
            </button>
            <button className="secondary" onClick={() => setImportOpen((current) => !current)}>
              <AppIcon name="download" />
              下载器
            </button>
            <button className="secondary icon-only" onClick={() => setSettingsOpen(true)} aria-label="设置">
              <AppIcon name="settings" />
            </button>
          </div>
        </header>

        {error ? <p className="error-banner">{error}</p> : null}

        {importOpen ? (
          <section className="download-drawer" aria-label="URL 下载">
            <div>
              <strong>从 URL 添加到本地视频中心</strong>
              <p>yt-dlp 后续会同步标题、缩略图、频道、简介和章节，现在先创建本地处理任务。</p>
            </div>
            <div className="url-import-row hub-url-row">
              <input
                placeholder="粘贴 YouTube / Bilibili / 公开视频 URL"
                value={videoUrl}
                onChange={(event) => setVideoUrl(event.currentTarget.value)}
                onKeyDown={(event) => {
                  if (event.key === "Enter") {
                    void handleUrlImport();
                  }
                }}
              />
              <button className="primary" onClick={handleUrlImport} disabled={busy}>
                <AppIcon name="link" />
                获取
              </button>
            </div>
          </section>
        ) : null}

        <section className="library-heading">
          <div>
            <h1>{activeNav === "processing" ? "处理队列" : "已完成视频"}</h1>
            <p>{activeNav === "processing" ? `${processingTasks.length} 个任务正在生成本地播放资产` : `${completedTasks.length} 个视频可直接播放`}</p>
          </div>
          <div className="view-toggle" aria-label="视图切换">
            <button className="active" type="button"><AppIcon name="grid" /></button>
            <button type="button"><AppIcon name="list" /></button>
          </div>
        </section>

        {activeNav !== "processing" ? (
          <>
            <div className="filter-row" role="tablist" aria-label="媒体筛选">
              {libraryFilters.map((filter) => (
                <button
                  className={libraryFilter === filter.id ? "active" : ""}
                  key={filter.id}
                  onClick={() => setLibraryFilter(filter.id)}
                  type="button"
                >
                  {filter.label}
                </button>
              ))}
            </div>

            <section className="video-grid" aria-label="本地视频列表">
              {visibleCards.length ? (
                visibleCards.map((card) => (
                  <article className="video-card" key={card.task.id} onClick={() => setStudyTaskId(card.task.id)}>
                    <div className={`video-thumbnail thumb-${card.thumbnailKind}`}>
                      <div className="thumb-gloss" />
                      <button className="thumb-play" aria-label={`播放 ${card.title}`} type="button">
                        <AppIcon name="play" />
                      </button>
                      <span className="duration-badge">{card.duration}</span>
                    </div>
                    <div className="video-card-body">
                      <div className="video-title-row">
                        <h2>{card.title}</h2>
                        <button
                          className="card-menu"
                          onClick={(event) => {
                            event.stopPropagation();
                            void handleOpenPath(exportTarget(card.task));
                          }}
                          aria-label="打开视频位置"
                          type="button"
                        >
                          <AppIcon name="more" />
                        </button>
                      </div>
                      <p className="channel-line">{card.channel}</p>
                      <div className="video-tags">
                        <span>{card.subtitleLabel}</span>
                        <span>已生成</span>
                      </div>
                      <p className="video-description">{card.description}</p>
                      <div className="video-meta">
                        <span>{card.added}</span>
                        <span>{card.resolution}</span>
                      </div>
                    </div>
                  </article>
                ))
              ) : (
                <div className="library-empty">
                  <h2>还没有可播放的视频</h2>
                  <p>导入本地视频或粘贴 URL 后，Echo 会把处理完成的视频排成媒体库卡片。</p>
                  <button className="primary" onClick={handleImport} disabled={busy}>
                    <AppIcon name="plus" />
                    导入第一个视频
                  </button>
                </div>
              )}
            </section>
          </>
        ) : null}

        <section className="processing-shelf">
          <div className="shelf-header">
            <h2>{activeNav === "processing" ? "全部处理任务" : `处理中 ${processingTasks.length} 个任务`}</h2>
            <button className="text-button" onClick={() => setActiveNav("processing")}>查看全部</button>
          </div>
          {processingTasks.length ? (
            <div className="processing-grid">
              {processingTasks.map((task) => (
                <article className={`processing-card ${task.status}`} key={task.id}>
                  <div className={`processing-thumb thumb-${task.thumbnailKind ?? "studio"}`} />
                  <div className="processing-info">
                    <div className="processing-title">
                      <strong>{task.title}</strong>
                      <span>{taskStatusSummary(task)}</span>
                    </div>
                    <p>{task.status === "failed" ? failedDetail(task) : task.detail}</p>
                    <div className="progress-track compact-progress" aria-label="任务进度">
                      <div style={{ width: `${Math.round((task.progress ?? 0) * 100)}%` }} />
                    </div>
                    <div className="processing-actions">
                      {task.status === "draft" || task.status === "paused" ? (
                        <button className="mini-button strong" onClick={() => void handleStartTask(task.id)}>
                          <AppIcon name="play" />
                          开始
                        </button>
                      ) : null}
                      {task.status === "running" ? (
                        <button className="mini-button" onClick={() => void handlePauseTask(task.id)}>
                          <AppIcon name="pause" />
                          暂停
                        </button>
                      ) : null}
                      {task.status === "failed" ? (
                        <button className="mini-button strong" onClick={() => void handleRetry(task.id)}>
                          <AppIcon name="retry" />
                          重试
                        </button>
                      ) : null}
                      <button className="mini-button" onClick={() => void handleOpenPath(exportTarget(task))}>
                        <AppIcon name="folder" />
                        位置
                      </button>
                      {canDeleteTask(task) ? (
                        <button className="mini-button danger" onClick={() => void handleDeleteTask(task.id)}>
                          <AppIcon name="trash" />
                          删除
                        </button>
                      ) : null}
                    </div>
                  </div>
                </article>
              ))}
            </div>
          ) : (
            <div className="empty-inline">当前没有处理中的任务。</div>
          )}
        </section>
      </section>

      {studyTask ? (
        <div className="modal-backdrop watch-backdrop" onMouseDown={() => setStudyTaskId(null)}>
          <section
            className="settings-modal study-modal watch-modal"
            role="dialog"
            aria-modal="true"
            aria-label="本地播放"
            onMouseDown={(event) => event.stopPropagation()}
          >
            <div className="modal-header watch-header">
              <button className="icon-button" onClick={() => setStudyTaskId(null)} aria-label="返回媒体库">
                <AppIcon name="arrowLeft" />
              </button>
              <div>
                <p className="modal-kicker">本地播放</p>
                <h2>{studyTask.title}</h2>
              </div>
              <div className="watch-actions">
                <button className="mini-button" onClick={() => void handleOpenPath(exportTarget(studyTask))}>
                  <AppIcon name="folder" />
                  位置
                </button>
                <button className="mini-button" onClick={() => void handleCopyPath(studyTask.outputDir ?? studyTask.assetDir)}>
                  <AppIcon name="copy" />
                  {copiedPath === (studyTask.outputDir ?? studyTask.assetDir) ? "已复制" : "复制路径"}
                </button>
              </div>
            </div>
            <StudySession task={studyTask} autoPlay />
          </section>
        </div>
      ) : null}

      {settingsOpen ? (
        <div className="modal-backdrop" onMouseDown={() => setSettingsOpen(false)}>
          <section className="settings-modal" role="dialog" aria-modal="true" aria-label="Echo 设置" onMouseDown={(event) => event.stopPropagation()}>
            <div className="modal-header">
              <div>
                <p className="modal-kicker">Settings</p>
                <h2>Echo 设置</h2>
              </div>
              <button className="icon-button" onClick={() => setSettingsOpen(false)} aria-label="关闭设置">
                x
              </button>
            </div>
            <div className="settings-form">
              <label>
                输出目录
                <div className="output-picker">
                  <input value={settings?.outputDir ?? "加载中..."} readOnly />
                  <button className="secondary" onClick={handleChooseOutputDir}>选择...</button>
                </div>
              </label>
              <div className="settings-note">翻译器：DeepSeek（MVP 固定）</div>
              <label>
                DeepSeek Base URL
                <input
                  value={settings?.deepseekBaseUrl ?? ""}
                  onChange={(event) => settings && setSettings({ ...settings, deepseekBaseUrl: event.currentTarget.value })}
                />
              </label>
              <label>
                API Key
                <input
                  type="password"
                  value={settings?.deepseekApiKey ?? ""}
                  onChange={(event) => settings && setSettings({ ...settings, deepseekApiKey: event.currentTarget.value })}
                />
              </label>
            </div>
            <div className="modal-actions">
              <button className="secondary" onClick={() => setSettingsOpen(false)}>取消</button>
              <button className="primary" onClick={async () => {
                await handleSaveTranslationSettings();
                setSettingsOpen(false);
              }}>保存</button>
            </div>
          </section>
        </div>
      ) : null}
    </main>
  );
}

export default App;
