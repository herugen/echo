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

type TaskFilter = "all" | "active" | "ready" | "failed";
type AppIconName = "file" | "link" | "settings" | "play" | "folder" | "copy" | "retry" | "pause" | "trash";

const taskFilters: Array<{ id: TaskFilter; label: string }> = [
  { id: "all", label: "全部" },
  { id: "active", label: "处理中" },
  { id: "ready", label: "待学习" },
  { id: "failed", label: "需处理" },
];

function AppIcon({ name }: { name: AppIconName }) {
  const paths: Record<AppIconName, string[]> = {
    file: ["M14 3H7a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h10a2 2 0 0 0 2-2V8Z", "M14 3v5h5"],
    link: ["M10 13a5 5 0 0 0 7.1 0l1.4-1.4a5 5 0 0 0-7.1-7.1l-.8.8", "M14 11a5 5 0 0 0-7.1 0l-1.4 1.4a5 5 0 0 0 7.1 7.1l.8-.8"],
    settings: ["M12 15.5a3.5 3.5 0 1 0 0-7 3.5 3.5 0 0 0 0 7Z", "M19 12a7 7 0 0 0-.1-1.2l2-1.5-2-3.4-2.4 1a7 7 0 0 0-2-1.2L14.2 3h-4.4l-.3 2.7a7 7 0 0 0-2 1.2l-2.4-1-2 3.4 2 1.5A7 7 0 0 0 5 12c0 .4 0 .8.1 1.2l-2 1.5 2 3.4 2.4-1a7 7 0 0 0 2 1.2l.3 2.7h4.4l.3-2.7a7 7 0 0 0 2-1.2l2.4 1 2-3.4-2-1.5c.1-.4.1-.8.1-1.2Z"],
    play: ["m8 5 11 7-11 7Z"],
    folder: ["M3 7a2 2 0 0 1 2-2h4l2 2h8a2 2 0 0 1 2 2v8a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2Z"],
    copy: ["M8 8h10v12H8Z", "M6 16H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h9a2 2 0 0 1 2 2v1"],
    retry: ["M4 4v6h6", "M20 20v-6h-6", "M5 15a7 7 0 0 0 12 3l3-4", "M19 9A7 7 0 0 0 7 6l-3 4"],
    pause: ["M8 5v14", "M16 5v14"],
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
  const [selectedTaskId, setSelectedTaskId] = useState<string | null>(null);
  const [studyTaskId, setStudyTaskId] = useState<string | null>(null);
  const [taskFilter, setTaskFilter] = useState<TaskFilter>("all");
  const [copiedPath, setCopiedPath] = useState<string | null>(null);
  const [settingsOpen, setSettingsOpen] = useState(false);
  const startingTasks = useRef<Set<string>>(new Set());
  const autoStartQueue = useRef<Set<string>>(new Set());

  const selectedTask = useMemo(
    () => tasks.find((task) => task.id === selectedTaskId) ?? null,
    [selectedTaskId, tasks],
  );
  const studyTask = useMemo(
    () => tasks.find((task) => task.id === studyTaskId && task.status === "succeeded") ?? null,
    [studyTaskId, tasks],
  );
  const taskCounts = useMemo(() => ({
    total: tasks.length,
    active: tasks.filter((task) => task.status === "running" || task.status === "draft" || task.status === "paused").length,
    ready: tasks.filter((task) => task.status === "succeeded").length,
    failed: tasks.filter((task) => task.status === "failed").length,
  }), [tasks]);
  const visibleTasks = useMemo(() => {
    if (taskFilter === "active") {
      return tasks.filter((task) => task.status === "running" || task.status === "draft" || task.status === "paused");
    }
    if (taskFilter === "ready") {
      return tasks.filter((task) => task.status === "succeeded");
    }
    if (taskFilter === "failed") {
      return tasks.filter((task) => task.status === "failed");
    }
    return tasks;
  }, [taskFilter, tasks]);
  const focusTask = selectedTask ?? visibleTasks[0] ?? tasks[0] ?? null;

  useEffect(() => {
    const handleKeyboardClipboard = async (event: KeyboardEvent) => {
      if ((!event.ctrlKey && !event.metaKey) || event.altKey) {
        return;
      }
      if (isTextField(event.target)) {
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
        setSelectedTaskId(null);
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
      setSelectedTaskId((current) => (current === taskId ? null : current));
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
        setSelectedTaskId(task.id);
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
      setSelectedTaskId(task.id);
      setVideoUrl("");
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
    <main className="app-shell">
      <header className="app-header">
        <div className="brand-lockup">
          <div className="brand-mark" aria-hidden="true">E</div>
          <div>
            <strong>Echo</strong>
            <span>本地双语视频学习工作台</span>
          </div>
        </div>
        <button className="ghost-button" onClick={() => setSettingsOpen(true)}>
          <AppIcon name="settings" />
          设置
        </button>
      </header>

      {error ? <p className="error-banner">{error}</p> : null}

      <section className="workspace-grid">
        <aside className="create-panel">
          <div className="panel-heading">
            <span>新任务</span>
            <h1>处理成字幕资产，再进入学习播放</h1>
          </div>

          <button className="primary action-button" onClick={handleImport} disabled={busy}>
            <AppIcon name="file" />
            {busy ? "创建中…" : "导入本地视频"}
          </button>

          <div className="url-card">
            <label htmlFor="video-url">在线视频链接</label>
            <div className="url-import-row">
              <input
                id="video-url"
                placeholder="粘贴 URL"
                value={videoUrl}
                onChange={(event) => setVideoUrl(event.currentTarget.value)}
                onKeyDown={(event) => {
                  if (event.key === "Enter") {
                    void handleUrlImport();
                  }
                }}
              />
              <button className="secondary icon-only" onClick={handleUrlImport} disabled={busy} aria-label="处理 URL">
                <AppIcon name="link" />
              </button>
            </div>
          </div>

          <div className="pipeline-card" aria-label="默认处理流程">
            {["获取", "转写", "翻译", "字幕", "学习"].map((step) => (
              <span key={step}>{step}</span>
            ))}
          </div>

          <div className="output-summary">
            <span>默认输出目录</span>
            <code>{settings?.outputDir ?? "加载中…"}</code>
            <button className="text-button" onClick={handleChooseOutputDir}>更改</button>
          </div>
        </aside>

        <section className="queue-panel">
          <div className="queue-header">
            <div>
              <span>任务队列</span>
              <h2>{taskCounts.total ? `${taskCounts.total} 个视频任务` : "准备第一个视频任务"}</h2>
            </div>
            <div className="queue-metrics" aria-label="任务概览">
              <span>{taskCounts.active} 处理中</span>
              <span>{taskCounts.ready} 待学习</span>
              <span>{taskCounts.failed} 需处理</span>
            </div>
          </div>

          <div className="filter-tabs" role="tablist" aria-label="任务筛选">
            {taskFilters.map((filter) => (
              <button
                className={taskFilter === filter.id ? "active" : ""}
                key={filter.id}
                onClick={() => setTaskFilter(filter.id)}
                type="button"
              >
                {filter.label}
              </button>
            ))}
          </div>

          <div className="task-list">
            {visibleTasks.length === 0 ? (
              <div className="empty-state">
                {tasks.length ? "这个筛选下暂时没有任务。" : "导入一个视频后，处理进度和学习入口会出现在这里。"}
              </div>
            ) : (
              visibleTasks.map((task) => {
                const artifacts = outputArtifacts(task);
                const isRunning = task.status === "running";
                const isDone = task.status === "succeeded";
                const isFailed = task.status === "failed";
                const isSelected = focusTask?.id === task.id;

                return (
                  <article
                    className={`task-row ${task.status} ${isSelected ? "selected" : ""}`}
                    key={task.id}
                    onClick={() => setSelectedTaskId(task.id)}
                  >
                    <div className="task-main">
                      <div className="task-title-line">
                        <strong>{task.title}</strong>
                        <span className={`status-badge ${task.status}`}>{taskStatusSummary(task)}</span>
                      </div>
                      <p>{isFailed ? failedDetail(task) : task.detail}</p>
                      <div className="progress-track compact-progress" aria-label="任务进度">
                        <div style={{ width: `${Math.round((task.progress ?? 0) * 100)}%` }} />
                      </div>
                      {isDone ? <p>{artifacts.length ? `${artifacts.length} 个产物可用` : "字幕产物可用"}</p> : null}
                      {isRunning && task.stages?.length ? (
                        <div className="stage-strip compact">
                          {task.stages.slice(0, 5).map((stage) => (
                            <span className={`stage-pill ${stage.status}`} key={stage.name}>{labelStage(stage.name)}</span>
                          ))}
                        </div>
                      ) : null}
                    </div>
                    <div className="task-actions">
                      {task.status === "draft" || task.status === "paused" ? (
                        <button className="mini-button" onClick={(event) => { event.stopPropagation(); void handleStartTask(task.id); }}>
                          <AppIcon name="play" />
                          开始
                        </button>
                      ) : null}
                      {task.status === "running" ? (
                        <button className="mini-button" onClick={(event) => { event.stopPropagation(); void handlePauseTask(task.id); }}>
                          <AppIcon name="pause" />
                          暂停
                        </button>
                      ) : null}
                      {isDone ? (
                        <button className="mini-button strong" onClick={(event) => { event.stopPropagation(); setStudyTaskId(task.id); }}>
                          <AppIcon name="play" />
                          学习
                        </button>
                      ) : null}
                      {isFailed ? (
                        <button className="mini-button" onClick={(event) => { event.stopPropagation(); void handleRetry(task.id); }}>
                          <AppIcon name="retry" />
                          重试
                        </button>
                      ) : null}
                    </div>
                  </article>
                );
              })
            )}
          </div>
        </section>

        <aside className="task-inspector" aria-label="当前任务详情">
          {focusTask ? (
            <>
              <div className="inspector-head">
                <span className={`status-badge ${focusTask.status}`}>{taskStatusSummary(focusTask)}</span>
                <h2>{focusTask.title}</h2>
                <p>{focusTask.status === "failed" ? failedDetail(focusTask) : focusTask.detail}</p>
              </div>

              <div className="progress-track detail-progress" aria-label="详情进度">
                <div style={{ width: `${Math.round((focusTask.progress ?? 0) * 100)}%` }} />
              </div>

              <div className="inspector-actions">
                {focusTask.status === "succeeded" ? (
                  <button className="primary" onClick={() => setStudyTaskId(focusTask.id)}>
                    <AppIcon name="play" />
                    学习播放
                  </button>
                ) : null}
                {focusTask.status === "draft" || focusTask.status === "paused" ? (
                  <button className="primary" onClick={() => void handleStartTask(focusTask.id)}>
                    <AppIcon name="play" />
                    开始处理
                  </button>
                ) : null}
                {focusTask.status === "running" ? (
                  <button className="secondary" onClick={() => void handlePauseTask(focusTask.id)}>
                    <AppIcon name="pause" />
                    暂停
                  </button>
                ) : null}
                {focusTask.status === "failed" ? (
                  <button className="primary" onClick={() => void handleRetry(focusTask.id)}>
                    <AppIcon name="retry" />
                    重试
                  </button>
                ) : null}
                <button className="secondary" onClick={() => void handleOpenPath(exportTarget(focusTask))}>
                  <AppIcon name="folder" />
                  打开位置
                </button>
                <button className="secondary" onClick={() => void handleCopyPath(focusTask.outputDir ?? focusTask.assetDir)}>
                  <AppIcon name="copy" />
                  {copiedPath === (focusTask.outputDir ?? focusTask.assetDir) ? "已复制" : "复制路径"}
                </button>
                {focusTask.status === "draft" || focusTask.status === "paused" || focusTask.status === "failed" ? (
                  <button className="secondary danger" onClick={() => void handleDeleteTask(focusTask.id)}>
                    <AppIcon name="trash" />
                    删除
                  </button>
                ) : null}
              </div>

              <div className="stage-log">
                {focusTask.stages?.length ? (
                  focusTask.stages.map((stage) => (
                    <div className={`stage-log-row ${stage.status}`} key={stage.name}>
                      <div className="stage-log-head">
                        <strong>{labelStage(stage.name)}</strong>
                        <span>{labelStatus(stage.status)}</span>
                      </div>
                      {stage.detail ? <p>{stage.detail}</p> : null}
                      {stage.artifacts?.length ? (
                        <ul>
                          {stage.artifacts.map((artifact) => (
                            <li key={artifact}>
                              <code>{artifact}</code>
                              <div className="artifact-actions">
                                <button className="text-button" onClick={() => void handleOpenPath(artifact)}>打开</button>
                                <button className="text-button" onClick={() => void handleCopyPath(artifact)}>
                                  {copiedPath === artifact ? "已复制" : "复制"}
                                </button>
                              </div>
                            </li>
                          ))}
                        </ul>
                      ) : null}
                    </div>
                  ))
                ) : (
                  <div className="empty-state compact">等待任务阶段写入。</div>
                )}
              </div>
            </>
          ) : (
            <div className="inspector-empty">
              <h2>还没有选中的任务</h2>
              <p>创建任务后，这里会显示处理阶段、产物路径和学习播放入口。</p>
            </div>
          )}
        </aside>
      </section>

      {studyTask ? (
        <div className="modal-backdrop" onMouseDown={() => setStudyTaskId(null)}>
          <section
            className="settings-modal study-modal"
            role="dialog"
            aria-modal="true"
            aria-label="学习播放"
            onMouseDown={(event) => event.stopPropagation()}
          >
            <div className="modal-header">
              <div>
                <p className="modal-kicker">学习播放</p>
                <h2>{studyTask.title}</h2>
              </div>
              <button className="icon-button" onClick={() => setStudyTaskId(null)} aria-label="关闭学习播放">
                ×
              </button>
            </div>
            <StudySession task={studyTask} />
          </section>
        </div>
      ) : null}

      {settingsOpen ? (
        <div className="modal-backdrop" onMouseDown={() => setSettingsOpen(false)}>
          <section className="settings-modal" role="dialog" aria-modal="true" aria-label="Echo 设置" onMouseDown={(event) => event.stopPropagation()}>
            <div className="modal-header">
              <div>
                <p className="eyebrow">Settings</p>
                <h2>Echo 设置</h2>
              </div>
              <button className="icon-button" onClick={() => setSettingsOpen(false)} aria-label="关闭设置">
                ×
              </button>
            </div>
            <div className="settings-form">
              <label>
                输出目录
                <div className="output-picker">
                  <input value={settings?.outputDir ?? "加载中…"} readOnly />
                  <button className="secondary" onClick={handleChooseOutputDir}>选择…</button>
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
