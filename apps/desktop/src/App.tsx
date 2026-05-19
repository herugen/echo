import { useEffect, useMemo, useRef, useState } from "react";
import { listen } from "@tauri-apps/api/event";
import "./App.css";
import { backend } from "./lib/backend";
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
  return task.stages?.flatMap((stage) => stage.artifacts ?? []) ?? [];
}

function exportTarget(task: TaskSummary): string {
  return outputArtifacts(task)[0] ?? task.outputDir ?? task.assetDir;
}

function isTextField(target: EventTarget | null): target is HTMLInputElement | HTMLTextAreaElement {
  return target instanceof HTMLInputElement || target instanceof HTMLTextAreaElement;
}

function replaceSelectedText(target: HTMLInputElement | HTMLTextAreaElement, text: string) {
  const start = target.selectionStart ?? target.value.length;
  const end = target.selectionEnd ?? target.value.length;
  target.setRangeText(text, start, end, "end");
  target.dispatchEvent(new Event("input", { bubbles: true }));
}

function App() {
  const [tasks, setTasks] = useState<TaskSummary[]>([]);
  const [settings, setSettings] = useState<AppSettings | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [videoUrl, setVideoUrl] = useState("");
  const [selectedTaskId, setSelectedTaskId] = useState<string | null>(null);
  const [copiedPath, setCopiedPath] = useState<string | null>(null);
  const [settingsOpen, setSettingsOpen] = useState(false);
  const startingTasks = useRef<Set<string>>(new Set());
  const autoStartQueue = useRef<Set<string>>(new Set());

  const selectedTask = useMemo(
    () => tasks.find((task) => task.id === selectedTaskId) ?? null,
    [selectedTaskId, tasks],
  );

  useEffect(() => {
    const handleKeyboardClipboard = async (event: KeyboardEvent) => {
      if ((!event.ctrlKey && !event.metaKey) || event.altKey) {
        return;
      }
      const key = event.key.toLowerCase();
      if (!["a", "c", "v", "x"].includes(key)) {
        return;
      }

      const target = event.target;
      if (isTextField(target)) {
        const start = target.selectionStart ?? 0;
        const end = target.selectionEnd ?? 0;
        const selectedText = target.value.slice(start, end);

        if (key === "a") {
          event.preventDefault();
          target.select();
          return;
        }
        if (key === "c" && selectedText) {
          event.preventDefault();
          await navigator.clipboard?.writeText(selectedText);
          return;
        }
        if (key === "x" && selectedText && !target.readOnly && !target.disabled) {
          event.preventDefault();
          await navigator.clipboard?.writeText(selectedText);
          replaceSelectedText(target, "");
          return;
        }
        if (key === "v" && !target.readOnly && !target.disabled) {
          const text = await navigator.clipboard?.readText();
          if (text !== undefined) {
            event.preventDefault();
            replaceSelectedText(target, text);
          }
        }
        return;
      }

      if (key === "c") {
        const selectedText = window.getSelection()?.toString();
        if (selectedText) {
          event.preventDefault();
          await navigator.clipboard?.writeText(selectedText);
        }
      }
    };

    window.addEventListener("keydown", handleKeyboardClipboard);
    return () => window.removeEventListener("keydown", handleKeyboardClipboard);
  }, []);

  useEffect(() => {
    Promise.all([backend.getSettings(), backend.listTasks()])
      .then(([nextSettings, nextTasks]) => {
        setSettings(nextSettings);
        setTasks(nextTasks);
        setSelectedTaskId(null);
      })
      .catch((cause) => setError(cause instanceof Error ? cause.message : "初始化失败"));

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
      <section className="command-panel">
        <button className="primary" onClick={handleImport} disabled={busy}>
          {busy ? "创建中…" : "导入本地视频"}
        </button>
        <button className="secondary" onClick={() => setSettingsOpen(true)}>
          设置
        </button>
        <div className="url-import-row command-url">
          <input
            placeholder="粘贴在线视频链接，由 yt-dlp 获取到本地后继续处理"
            value={videoUrl}
            onChange={(event) => setVideoUrl(event.currentTarget.value)}
            onKeyDown={(event) => {
              if (event.key === "Enter") {
                void handleUrlImport();
              }
            }}
          />
          <button className="secondary" onClick={handleUrlImport} disabled={busy}>
            处理 URL
          </button>
        </div>
        {error ? <p className="error-banner">{error}</p> : null}
      </section>

      <section className="panel task-list">
        <div className="panel-header">
          <h2>任务列表</h2>
          <span>{tasks.length} 个任务</span>
        </div>
        {tasks.length === 0 ? (
          <div className="empty-state">还没有任务。先导入一个本地视频，或者粘贴一个 URL。</div>
        ) : (
          tasks.map((task) => {
            const artifacts = outputArtifacts(task);
            const isRunning = task.status === "running";
            const isDone = task.status === "succeeded";
            const isFailed = task.status === "failed";

            return (
              <div className={`task-row ${task.status}`} key={task.id} onClick={() => setSelectedTaskId(task.id)}>
                <div className="task-main">
                  <div className="task-title-line">
                    <strong>{task.title}</strong>
                    <span className={`status-badge ${task.status}`}>{taskStatusSummary(task)}</span>
                  </div>
                  <p>{isFailed ? failedDetail(task) : task.detail}</p>
                  {isRunning ? (
                    <>
                      <div className="progress-track compact-progress" aria-label="任务进度">
                        <div style={{ width: `${Math.round((task.progress ?? 0) * 100)}%` }} />
                      </div>
                      {task.stages?.length ? (
                        <div className="stage-strip compact">
                          {task.stages.map((stage) => (
                            <span className={`stage-pill ${stage.status}`} key={stage.name}>{labelStage(stage.name)}</span>
                          ))}
                        </div>
                      ) : null}
                    </>
                  ) : null}
                  {isDone && artifacts.length ? <p>{artifacts.length} 个产物已导出</p> : null}
                </div>
                <div className="task-actions">
                  {task.status === "draft" || task.status === "paused" ? (
                    <button className="mini-button" onClick={(event) => { event.stopPropagation(); void handleStartTask(task.id); }}>开始</button>
                  ) : null}
                  {task.status === "running" ? (
                    <button className="mini-button" onClick={(event) => { event.stopPropagation(); void handlePauseTask(task.id); }}>暂停</button>
                  ) : null}
                  {isDone ? (
                    <button className="mini-button" onClick={(event) => { event.stopPropagation(); void handleOpenPath(exportTarget(task)); }}>导出结果</button>
                  ) : null}
                  {isFailed ? (
                    <button className="mini-button" onClick={(event) => { event.stopPropagation(); void handleRetry(task.id); }}>重试</button>
                  ) : null}
                  {task.status === "draft" || task.status === "paused" || task.status === "failed" ? (
                    <button className="mini-button danger" onClick={(event) => { event.stopPropagation(); void handleDeleteTask(task.id); }}>删除</button>
                  ) : null}
                </div>
              </div>
            );
          })
        )}
      </section>

      {selectedTask ? (
        <div className="modal-backdrop" onMouseDown={() => setSelectedTaskId(null)}>
          <section className="settings-modal task-detail-modal" role="dialog" aria-modal="true" aria-label="任务详情" onMouseDown={(event) => event.stopPropagation()}>
            <div className="modal-header">
              <div>
                <p className="eyebrow">Task Detail</p>
                <h2>{selectedTask.title}</h2>
              </div>
              <button className="icon-button" onClick={() => setSelectedTaskId(null)} aria-label="关闭任务详情">
                ×
              </button>
            </div>
            <div className="task-detail">
              <div className="path-card">
                <span>{labelStatus(selectedTask.status)}</span>
                <code>{selectedTask.outputDir}</code>
                <div className="path-actions">
                  {selectedTask.status === "draft" || selectedTask.status === "paused" ? (
                    <button className="mini-button" onClick={() => void handleStartTask(selectedTask.id)}>开始处理</button>
                  ) : null}
                  {selectedTask.status === "running" ? (
                    <button className="mini-button" onClick={() => void handlePauseTask(selectedTask.id)}>暂停</button>
                  ) : null}
                  {selectedTask.status === "failed" ? (
                    <button className="mini-button" onClick={() => void handleRetry(selectedTask.id)}>重试</button>
                  ) : null}
                  {selectedTask.status === "draft" || selectedTask.status === "paused" || selectedTask.status === "failed" ? (
                    <button className="mini-button danger" onClick={() => void handleDeleteTask(selectedTask.id)}>删除任务</button>
                  ) : null}
                  {selectedTask.status === "succeeded" ? (
                    <button className="mini-button" onClick={() => void handleOpenPath(exportTarget(selectedTask))}>导出结果</button>
                  ) : null}
                  <button className="mini-button" onClick={() => void handleOpenPath(selectedTask.outputDir ?? selectedTask.assetDir)}>打开输出位置</button>
                  <button className="mini-button" onClick={() => void handleCopyPath(selectedTask.outputDir ?? selectedTask.assetDir)}>
                    {copiedPath === (selectedTask.outputDir ?? selectedTask.assetDir) ? "已复制" : "复制路径"}
                  </button>
                </div>
              </div>
              <div className="progress-track detail-progress" aria-label="详情进度">
                <div style={{ width: `${Math.round((selectedTask.progress ?? 0) * 100)}%` }} />
              </div>
              <div className="stage-log">
                {selectedTask.stages?.map((stage) => (
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
                ))}
              </div>
            </div>
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
