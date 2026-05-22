import { type CSSProperties, useEffect, useMemo, useRef, useState } from "react";
import { convertFileSrc, isTauri as tauriIsTauri } from "@tauri-apps/api/core";
import { getCurrentWindow } from "@tauri-apps/api/window";
import { MediaCaptions, MediaOutlet, MediaPlayer } from "@vidstack/react";
import type { TextTrackInit } from "vidstack";
import "vidstack/styles/defaults.css";
import "vidstack/styles/ui/captions.css";
import { backend } from "./lib/backend";
import { formatClock, mergeSubtitleTracks, subtitleCuesToWebVtt } from "./lib/subtitles";
import type { SubtitleCue, TaskSummary } from "./types";

type IconName =
  | "previous"
  | "next"
  | "play"
  | "pause"
  | "replay"
  | "loop"
  | "captions"
  | "settings"
  | "fullscreen"
  | "fullscreenExit";
type CaptionTrackId = "off" | "source" | "translated" | "bilingual";
type CaptionFileTrackId = Exclude<CaptionTrackId, "off">;

interface CaptionTrackSource {
  id: CaptionFileTrackId;
  label: string;
  language: string;
  path?: string;
}

interface StudyData {
  videoPath?: string;
  videoUrl: string;
  sourceSubtitlePath?: string;
  translatedSubtitlePath?: string;
  bilingualSubtitlePath?: string;
  captionTracks: CaptionTrackSource[];
  cues: SubtitleCue[];
}

interface StudySessionProps {
  task: TaskSummary;
}

type VidstackDetailEvent<T> = Event & { detail: T };
type StudyMediaPlayerElement = HTMLElement & {
  currentTime: number;
  paused: boolean;
  playbackRate: number;
  play(): Promise<void>;
  pause(): Promise<void>;
  enterFullscreen(): Promise<void>;
  exitFullscreen(): Promise<void>;
};

const VIDEO_EXTENSION = /\.(mp4|m4v|mov|mkv|webm|avi)(?:$|\?)/i;
const PLAYBACK_RATES = [0.75, 1, 1.25];
const EMPTY_CUES: SubtitleCue[] = [];
const EMPTY_CAPTION_TRACKS: CaptionTrackSource[] = [];
const isTauriRuntime = tauriIsTauri();

function ControlIcon({ name }: { name: IconName }) {
  if (name === "previous") {
    return (
      <svg viewBox="0 0 24 24" aria-hidden="true">
        <path d="M19 5v14M16 6l-9 6 9 6V6Z" />
      </svg>
    );
  }
  if (name === "next") {
    return (
      <svg viewBox="0 0 24 24" aria-hidden="true">
        <path d="M5 5v14M8 6l9 6-9 6V6Z" />
      </svg>
    );
  }
  if (name === "pause") {
    return (
      <svg viewBox="0 0 24 24" aria-hidden="true">
        <path d="M8 6v12M16 6v12" />
      </svg>
    );
  }
  if (name === "replay") {
    return (
      <svg viewBox="0 0 24 24" aria-hidden="true">
        <path d="M8 7H4V3M4.6 11a8 8 0 1 0 2.1-5.4L4 8.2" />
      </svg>
    );
  }
  if (name === "loop") {
    return (
      <svg viewBox="0 0 24 24" aria-hidden="true">
        <path d="M7 7h8a4 4 0 0 1 4 4v1M17 5l2 2-2 2M17 17H9a4 4 0 0 1-4-4v-1M7 19l-2-2 2-2" />
      </svg>
    );
  }
  if (name === "captions") {
    return (
      <svg viewBox="0 0 24 24" aria-hidden="true">
        <path d="M4 6h16v12H4zM8 11h3M13 11h3M8 15h8" />
      </svg>
    );
  }
  if (name === "settings") {
    return (
      <svg viewBox="0 0 24 24" aria-hidden="true">
        <path d="M12 15.5a3.5 3.5 0 1 0 0-7 3.5 3.5 0 0 0 0 7Z" />
        <path d="M19.4 15a1.7 1.7 0 0 0 .34 1.88l.05.05a2.05 2.05 0 1 1-2.9 2.9l-.05-.05A1.7 1.7 0 0 0 15 19.4a1.7 1.7 0 0 0-1 .6v.14a2.05 2.05 0 1 1-4.1 0V20a1.7 1.7 0 0 0-1-.6 1.7 1.7 0 0 0-1.88.34l-.05.05a2.05 2.05 0 1 1-2.9-2.9l.05-.05A1.7 1.7 0 0 0 4.6 15a1.7 1.7 0 0 0-.6-1H3.86a2.05 2.05 0 1 1 0-4.1H4a1.7 1.7 0 0 0 .6-1 1.7 1.7 0 0 0-.34-1.88l-.05-.05a2.05 2.05 0 1 1 2.9-2.9l.05.05A1.7 1.7 0 0 0 9 4.6a1.7 1.7 0 0 0 1-.6v-.14a2.05 2.05 0 1 1 4.1 0V4a1.7 1.7 0 0 0 1 .6 1.7 1.7 0 0 0 1.88-.34l.05-.05a2.05 2.05 0 1 1 2.9 2.9l-.05.05A1.7 1.7 0 0 0 19.4 9c.2.36.4.68.6 1h.14a2.05 2.05 0 1 1 0 4.1H20a1.7 1.7 0 0 0-.6.9Z" />
      </svg>
    );
  }
  if (name === "fullscreen") {
    return (
      <svg viewBox="0 0 24 24" aria-hidden="true">
        <path d="M8 3H3v5M16 3h5v5M21 16v5h-5M3 16v5h5M3 3l6 6M21 3l-6 6M21 21l-6-6M3 21l6-6" />
      </svg>
    );
  }
  if (name === "fullscreenExit") {
    return (
      <svg viewBox="0 0 24 24" aria-hidden="true">
        <path d="M9 3v6H3M15 3v6h6M21 15h-6v6M3 15h6v6M3 9l6-6M21 9l-6-6M21 15l-6 6M3 15l6 6" />
      </svg>
    );
  }
  return (
    <svg viewBox="0 0 24 24" aria-hidden="true">
      <path d="m8 5 10 7-10 7V5Z" />
    </svg>
  );
}

function allArtifacts(task: TaskSummary): string[] {
  return task.stages?.flatMap((stage) => stage.artifacts ?? []).filter(Boolean) ?? [];
}

function findStageArtifact(task: TaskSummary, stageName: string, predicate?: (artifact: string) => boolean): string | undefined {
  const artifacts = task.stages?.find((stage) => stage.name === stageName)?.artifacts ?? [];
  return predicate ? artifacts.find(predicate) : artifacts[0];
}

function isVideoPath(path: string): boolean {
  return VIDEO_EXTENSION.test(path);
}

function resolveVideoUrl(path?: string): string {
  if (!path) {
    return "";
  }
  if (/^https?:\/\//i.test(path)) {
    return path;
  }
  return isTauriRuntime ? convertFileSrc(path) : "";
}

function resolveVideoMimeType(path?: string): string | undefined {
  if (!path) {
    return undefined;
  }
  const cleanPath = path.split("?")[0].toLowerCase();
  if (cleanPath.endsWith(".m3u8")) {
    return "application/x-mpegurl";
  }
  if (cleanPath.endsWith(".mp4") || cleanPath.endsWith(".m4v")) {
    return "video/mp4";
  }
  if (cleanPath.endsWith(".mov")) {
    return "video/quicktime";
  }
  if (cleanPath.endsWith(".webm")) {
    return "video/webm";
  }
  if (cleanPath.endsWith(".mkv")) {
    return "video/x-matroska";
  }
  if (cleanPath.endsWith(".avi")) {
    return "video/x-msvideo";
  }
  return undefined;
}

async function readOptionalSubtitle(path?: string): Promise<string> {
  if (!path) {
    return "";
  }

  try {
    return await backend.readTextFile(path);
  } catch {
    return "";
  }
}

function getStudyPaths(task: TaskSummary) {
  const acquiredVideo = findStageArtifact(task, "acquire_input", isVideoPath);
  const exportedVideo = allArtifacts(task).find(isVideoPath);
  return {
    videoPath: acquiredVideo ?? exportedVideo,
    sourceSubtitlePath: findStageArtifact(task, "generate_source_subtitles"),
    translatedSubtitlePath: findStageArtifact(task, "generate_translated_subtitles"),
    bilingualSubtitlePath: findStageArtifact(task, "generate_bilingual_subtitles"),
  };
}

function buildCaptionTracks(
  paths: ReturnType<typeof getStudyPaths>,
  sourceText: string,
  translatedText: string,
  bilingualText: string,
): CaptionTrackSource[] {
  const tracks: CaptionTrackSource[] = [
    {
      id: "bilingual",
      label: "双语字幕",
      language: "zh-CN",
      path: paths.bilingualSubtitlePath,
    },
    {
      id: "source",
      label: "原文字幕",
      language: "en",
      path: paths.sourceSubtitlePath,
    },
    {
      id: "translated",
      label: "译文字幕",
      language: "zh-CN",
      path: paths.translatedSubtitlePath,
    },
  ];

  const hasText: Record<CaptionFileTrackId, boolean> = {
    bilingual: !!bilingualText.trim(),
    source: !!sourceText.trim(),
    translated: !!translatedText.trim(),
  };

  return tracks.filter((track) => track.path && hasText[track.id]);
}

function getDefaultCaptionId(tracks: CaptionTrackSource[]): CaptionTrackId {
  return tracks.find((track) => track.id === "bilingual")?.id ?? tracks[0]?.id ?? "off";
}

async function loadStudyData(task: TaskSummary): Promise<StudyData> {
  const paths = getStudyPaths(task);
  const [sourceText, translatedText, bilingualText] = await Promise.all([
    readOptionalSubtitle(paths.sourceSubtitlePath),
    readOptionalSubtitle(paths.translatedSubtitlePath),
    readOptionalSubtitle(paths.bilingualSubtitlePath),
  ]);
  const cues = mergeSubtitleTracks(sourceText, translatedText, bilingualText);

  if (!cues.length) {
    throw new Error("没有找到可用于学习的字幕产物。");
  }

  return {
    ...paths,
    videoUrl: resolveVideoUrl(paths.videoPath),
    captionTracks: buildCaptionTracks(paths, sourceText, translatedText, bilingualText),
    cues,
  };
}

function findCueIndexAtTime(cues: SubtitleCue[], time: number): number {
  return cues.findIndex((cue) => time >= cue.start && time < cue.end + 0.08);
}

function findNearestCueIndex(cues: SubtitleCue[], time: number): number {
  const exact = findCueIndexAtTime(cues, time);
  if (exact !== -1) {
    return exact;
  }

  let previous = -1;
  for (let index = 0; index < cues.length; index += 1) {
    if (time >= cues[index].start) {
      previous = index;
    } else {
      break;
    }
  }
  return previous;
}

export function StudySession({ task }: StudySessionProps) {
  const playerRef = useRef<StudyMediaPlayerElement | null>(null);
  const videoFrameRef = useRef<HTMLDivElement | null>(null);
  const subtitleRefs = useRef<Record<string, HTMLDivElement | null>>({});
  const hideControlsTimer = useRef<number | null>(null);
  const controlsFocusedRef = useRef(false);
  const [data, setData] = useState<StudyData | null>(null);
  const [loading, setLoading] = useState(true);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [videoError, setVideoError] = useState<string | null>(null);
  const [currentTime, setCurrentTime] = useState(0);
  const [duration, setDuration] = useState(0);
  const [paused, setPaused] = useState(true);
  const [loopCue, setLoopCue] = useState(false);
  const [playbackRate, setPlaybackRate] = useState(1);
  const [controlsVisible, setControlsVisible] = useState(true);
  const [isFullscreen, setIsFullscreen] = useState(false);
  const [fullscreenMode, setFullscreenMode] = useState<"dom" | "player" | "window" | null>(null);

  useEffect(() => {
    let alive = true;
    setLoading(true);
    setLoadError(null);
    setVideoError(null);
    setCurrentTime(0);
    setDuration(0);
    setPaused(true);
    setControlsVisible(true);
    setLoopCue(false);
    setPlaybackRate(1);
    setFullscreenMode(null);
    setIsFullscreen(false);
    subtitleRefs.current = {};

    loadStudyData(task)
      .then((nextData) => {
        if (!alive) return;
        setData(nextData);
        setLoading(false);
      })
      .catch((cause) => {
        if (!alive) return;
        setData(null);
        setLoadError(cause instanceof Error ? cause.message : "学习视图加载失败。");
        setLoading(false);
      });

    return () => {
      alive = false;
    };
  }, [task]);

  useEffect(() => {
    if (playerRef.current) {
      playerRef.current.playbackRate = playbackRate;
    }
  }, [playbackRate, data?.videoUrl]);

  const cues = data?.cues ?? EMPTY_CUES;
  const captionTracks = data?.captionTracks ?? EMPTY_CAPTION_TRACKS;
  const activeCueIndex = useMemo(() => findNearestCueIndex(cues, currentTime), [cues, currentTime]);
  const activeCue = activeCueIndex >= 0 ? cues[activeCueIndex] : null;
  const timelineEnd = Math.max(duration || 0, cues[cues.length - 1]?.end || 0, 1);
  const progressPercent = Math.max(0, Math.min(100, (Math.min(currentTime, timelineEnd) / timelineEnd) * 100));
  const mediaSource = useMemo(() => {
    if (!data?.videoUrl) {
      return "";
    }
    const type = resolveVideoMimeType(data.videoPath ?? data.videoUrl);
    return type ? { src: data.videoUrl, type } : data.videoUrl;
  }, [data?.videoPath, data?.videoUrl]);
  const vidstackTextTracks = useMemo<TextTrackInit[]>(() => {
    const defaultCaptionId = getDefaultCaptionId(captionTracks);
    return captionTracks.flatMap((track) => {
      const vtt = subtitleCuesToWebVtt(cues, track.id);
      if (!vtt) {
        return [];
      }
      return [
        {
          id: track.id,
          kind: "subtitles" as const,
          label: track.label,
          language: track.language,
          content: vtt,
          type: "vtt" as const,
          default: track.id === defaultCaptionId,
        },
      ];
    });
  }, [captionTracks, cues]);

  useEffect(() => {
    const handleFullscreenChange = () => {
      const isFrameFullscreen = document.fullscreenElement === videoFrameRef.current;
      const player = playerRef.current;
      const isPlayerFullscreen =
        !!player && (document.fullscreenElement === player || (document.fullscreenElement instanceof Node && player.contains(document.fullscreenElement)));
      if (isFrameFullscreen || isPlayerFullscreen) {
        setFullscreenMode("dom");
        setIsFullscreen(true);
        revealControls();
      } else if (fullscreenMode === "dom" || fullscreenMode === "player") {
        setFullscreenMode(null);
        setIsFullscreen(false);
        revealControls();
      }
    };

    document.addEventListener("fullscreenchange", handleFullscreenChange);
    return () => {
      document.removeEventListener("fullscreenchange", handleFullscreenChange);
    };
  }, [fullscreenMode]);

  useEffect(() => {
    revealControls();
    return () => {
      if (hideControlsTimer.current !== null) {
        window.clearTimeout(hideControlsTimer.current);
      }
    };
  }, [paused, videoError, data?.videoUrl]);

  useEffect(() => {
    if (!activeCue) {
      return;
    }
    subtitleRefs.current[activeCue.id]?.scrollIntoView({ block: "center", behavior: "smooth" });
  }, [activeCue]);

  useEffect(() => {
    const handleStudyShortcuts = (event: KeyboardEvent) => {
      if (!data?.videoUrl || event.defaultPrevented || event.altKey || event.ctrlKey || event.metaKey) {
        return;
      }
      const target = event.target;
      if (
        target instanceof HTMLInputElement ||
        target instanceof HTMLTextAreaElement ||
        target instanceof HTMLSelectElement ||
        (target instanceof HTMLElement && target.isContentEditable)
      ) {
        return;
      }

      if (event.key === "[") {
        event.preventDefault();
        skipCue(-1);
      } else if (event.key === "]") {
        event.preventDefault();
        skipCue(1);
      } else if (event.key.toLowerCase() === "r") {
        event.preventDefault();
        replayCurrentCue();
      } else if (event.key.toLowerCase() === "l") {
        event.preventDefault();
        setLoopCue((current) => !current);
        revealControls();
      }
    };

    window.addEventListener("keydown", handleStudyShortcuts);
    return () => window.removeEventListener("keydown", handleStudyShortcuts);
  }, [activeCueIndex, cues, data?.videoUrl]);

  function clearControlsHideTimer() {
    if (hideControlsTimer.current !== null) {
      window.clearTimeout(hideControlsTimer.current);
      hideControlsTimer.current = null;
    }
  }

  function scheduleControlsHide(delay = 2200) {
    clearControlsHideTimer();
    setControlsVisible(true);
    if (paused || videoError || !data?.videoUrl || controlsFocusedRef.current) {
      return;
    }
    hideControlsTimer.current = window.setTimeout(() => {
      setControlsVisible(false);
    }, delay);
  }

  function revealControls() {
    scheduleControlsHide();
  }

  function handleOverlayFocus() {
    controlsFocusedRef.current = true;
    clearControlsHideTimer();
    setControlsVisible(true);
  }

  function handleOverlayBlur(event: React.FocusEvent<HTMLDivElement>) {
    const nextTarget = event.relatedTarget;
    if (nextTarget instanceof Node && event.currentTarget.contains(nextTarget)) {
      return;
    }
    controlsFocusedRef.current = false;
    scheduleControlsHide(900);
  }

  async function toggleFullscreen() {
    revealControls();
    try {
      if (isFullscreen) {
        if (fullscreenMode === "window" && isTauriRuntime) {
          await getCurrentWindow().setFullscreen(false);
        } else if (fullscreenMode === "player" && playerRef.current) {
          await playerRef.current.exitFullscreen();
        } else if (fullscreenMode === "dom" && document.fullscreenElement) {
          await document.exitFullscreen();
        }
        setFullscreenMode(null);
        setIsFullscreen(false);
        setVideoError(null);
        return;
      }

      if (isTauriRuntime) {
        await getCurrentWindow().setFullscreen(true);
        setFullscreenMode("window");
        setIsFullscreen(true);
        setVideoError(null);
        return;
      }

      if (playerRef.current) {
        await playerRef.current.enterFullscreen();
        setFullscreenMode("player");
        setIsFullscreen(true);
        setVideoError(null);
        return;
      }

      const frame = videoFrameRef.current;
      if (document.fullscreenEnabled && frame?.requestFullscreen) {
        await frame.requestFullscreen();
        setFullscreenMode("dom");
        setIsFullscreen(true);
        setVideoError(null);
        return;
      }

      setVideoError("当前环境不支持全屏播放。");
    } catch {
      setVideoError(isFullscreen ? "无法退出全屏播放。" : "无法进入全屏播放，请检查系统全屏权限。");
    }
  }

  function selectPlaybackRate(rate: number) {
    setPlaybackRate(rate);
    revealControls();
  }

  function seekTo(time: number) {
    const nextTime = Math.max(0, Math.min(time, timelineEnd));
    setCurrentTime(nextTime);
    if (playerRef.current) {
      playerRef.current.currentTime = nextTime;
    }
  }

  function seekToCue(index: number, shouldPlay = true) {
    const cue = cues[index];
    if (!cue) {
      return;
    }
    seekTo(cue.start + 0.02);
    if (shouldPlay && playerRef.current) {
      playVideo();
    }
  }

  function replayCurrentCue() {
    seekToCue(activeCueIndex >= 0 ? activeCueIndex : 0);
  }

  function skipCue(delta: number) {
    const nextIndex = Math.max(0, Math.min(cues.length - 1, (activeCueIndex >= 0 ? activeCueIndex : 0) + delta));
    seekToCue(nextIndex);
  }

  function handleCueKeyDown(event: React.KeyboardEvent<HTMLDivElement>, index: number) {
    if (event.key !== "Enter" && event.key !== " ") {
      return;
    }
    event.preventDefault();
    seekToCue(index);
  }

  function togglePlayback() {
    const player = playerRef.current;
    if (!player) {
      return;
    }
    if (player.paused) {
      playVideo();
    } else {
      player.pause();
    }
  }

  function playVideo() {
    const player = playerRef.current;
    if (!player) {
      return;
    }
    player.play().catch(() => {
      setPaused(true);
      setVideoError("视频暂时无法播放，请稍后重试。");
    });
  }

  function handleTimeUpdate(event: Event) {
    const nextTime = (event as VidstackDetailEvent<{ currentTime: number }>).detail.currentTime;
    if (loopCue) {
      const cueIndex = findCueIndexAtTime(cues, nextTime);
      const cue = cues[cueIndex];
      if (cue && cue.end - cue.start > 0.2 && nextTime >= cue.end - 0.06) {
        const restartTime = cue.start + 0.02;
        if (playerRef.current) {
          playerRef.current.currentTime = restartTime;
        }
        setCurrentTime(restartTime);
        return;
      }
    }
    setCurrentTime(nextTime);
  }

  function handleCanPlay(event: Event) {
    setDuration((event as VidstackDetailEvent<{ duration: number }>).detail.duration || 0);
    setVideoError(null);
  }

  function handleDurationChange(event: Event) {
    setDuration((event as VidstackDetailEvent<number>).detail || 0);
  }

  function handleRateChange(event: Event) {
    setPlaybackRate((event as VidstackDetailEvent<number>).detail || 1);
  }

  function handlePlayerFullscreenChange(event: Event) {
    if (fullscreenMode === "window") {
      return;
    }
    const isPlayerFullscreen = (event as VidstackDetailEvent<boolean>).detail;
    setFullscreenMode(isPlayerFullscreen ? "player" : null);
    setIsFullscreen(isPlayerFullscreen);
    revealControls();
  }

  function handlePlayerError(event: Event) {
    const detail = (event as VidstackDetailEvent<{ message?: string }>).detail;
    setVideoError(detail?.message || "视频文件无法在当前窗口播放。");
  }

  function handlePlayFail() {
    setPaused(true);
    setVideoError("视频暂时无法播放，请稍后重试。");
  }

  function handleFullscreenFallback() {
    if (isTauriRuntime && !isFullscreen) {
      void toggleFullscreen();
      return;
    }
    setVideoError(isFullscreen ? "无法退出全屏播放。" : "无法进入全屏播放，请检查系统全屏权限。");
  }

  if (loading) {
    return <div className="study-loading">正在打开学习视图…</div>;
  }

  if (loadError || !data) {
    return <div className="study-empty">{loadError ?? "学习视图不可用。"}</div>;
  }

  return (
    <div className={`study-session ${isFullscreen ? "player-fullscreen" : ""}`}>
      <div className="study-main">
        <section className="study-video-panel" aria-label="视频播放器">
          <div
            ref={videoFrameRef}
            className={`study-video-frame ${controlsVisible ? "" : "controls-hidden"}`}
            onPointerMove={() => revealControls()}
            onPointerDown={() => revealControls()}
            onMouseLeave={() => scheduleControlsHide(700)}
          >
            {data.videoUrl ? (
              <MediaPlayer
                ref={playerRef}
                className="study-media-player"
                data-testid="study-media-player"
                src={mediaSource}
                title={task.title}
                viewType="video"
                load="eager"
                preload="metadata"
                playsinline
                playbackRate={playbackRate}
                textTracks={vidstackTextTracks}
                keyTarget="player"
                onCanPlay={handleCanPlay}
                onDurationChange={handleDurationChange}
                onTimeUpdate={handleTimeUpdate}
                onRateChange={handleRateChange}
                onPlay={() => setPaused(false)}
                onPause={() => setPaused(true)}
                onEnded={() => setPaused(true)}
                onError={handlePlayerError}
                onPlayFail={handlePlayFail}
                onFullscreenChange={handlePlayerFullscreenChange}
                onFullscreenError={handleFullscreenFallback}
              >
                <MediaOutlet />
                <MediaCaptions />
              </MediaPlayer>
            ) : (
              <div className="study-video-placeholder">未找到可播放的视频文件</div>
            )}
            {videoError ? <div className="study-video-error">{videoError}</div> : null}

            <div
              className={`study-learning-dock ${controlsVisible ? "" : "hidden"}`}
              data-testid="study-learning-dock"
              onFocusCapture={handleOverlayFocus}
              onBlurCapture={handleOverlayBlur}
            >
              <div className="study-cue-meter">
                <span>{activeCue ? formatClock(activeCue.start) : formatClock(currentTime)}</span>
                <strong>{activeCueIndex >= 0 ? `${activeCueIndex + 1}/${cues.length}` : "0/0"}</strong>
              </div>
              <div className="study-rate-switch" role="group" aria-label="播放速度">
                {PLAYBACK_RATES.map((rate) => (
                  <button className={playbackRate === rate ? "active" : ""} key={rate} onClick={() => selectPlaybackRate(rate)}>
                    {rate}x
                  </button>
                ))}
              </div>
            </div>

            <div className="study-player-overlay" onFocusCapture={handleOverlayFocus} onBlurCapture={handleOverlayBlur}>
              <div className="study-progress-row">
                <input
                  aria-label="学习进度"
                  type="range"
                  min="0"
                  max={timelineEnd}
                  step="0.05"
                  value={Math.min(currentTime, timelineEnd)}
                  style={{ "--study-progress": `${progressPercent}%` } as CSSProperties}
                  onChange={(event) => seekTo(Number(event.currentTarget.value))}
                />
              </div>

              <div className="study-control-dock">
                <div className="study-control-bar">
                  <div className="study-controls">
                    <button className="play-button" onClick={togglePlayback} aria-label={paused ? "播放" : "暂停"} disabled={!data.videoUrl}>
                      <ControlIcon name={paused ? "play" : "pause"} />
                    </button>
                    <button className="icon-tool" onClick={() => skipCue(-1)} aria-label="上一句">
                      <ControlIcon name="previous" />
                    </button>
                    <button className="icon-tool" onClick={replayCurrentCue} aria-label="重播当前句">
                      <ControlIcon name="replay" />
                    </button>
                    <button className="icon-tool" onClick={() => skipCue(1)} aria-label="下一句">
                      <ControlIcon name="next" />
                    </button>
                    <button
                      className={`icon-tool loop-tool ${loopCue ? "active" : ""}`}
                      onClick={() => {
                        setLoopCue((current) => !current);
                        revealControls();
                      }}
                      aria-label={loopCue ? "关闭单句循环" : "循环当前句"}
                    >
                      <ControlIcon name="loop" />
                    </button>
                    <span className="study-time-label">
                      {formatClock(currentTime)} / {formatClock(timelineEnd)}
                    </span>
                  </div>

                  <div className="study-control-tools">
                    <button className="icon-tool" onClick={toggleFullscreen} aria-label={isFullscreen ? "退出全屏" : "全屏播放"}>
                      <ControlIcon name={isFullscreen ? "fullscreenExit" : "fullscreen"} />
                    </button>
                  </div>
                </div>
              </div>
            </div>
          </div>
        </section>

        <section className="subtitle-panel" aria-label="同步字幕">
          {cues.map((cue, index) => (
            <div
              className={`subtitle-card ${index === activeCueIndex ? "active" : ""}`}
              key={cue.id}
              role="button"
              tabIndex={0}
              ref={(node) => {
                subtitleRefs.current[cue.id] = node;
              }}
              onClick={() => seekToCue(index)}
              onKeyDown={(event) => handleCueKeyDown(event, index)}
            >
              <span className="subtitle-time">{formatClock(cue.start)}</span>
              <span className="subtitle-source">{cue.source}</span>
              {cue.translation ? <span className="subtitle-translation">{cue.translation}</span> : null}
            </div>
          ))}
        </section>
      </div>
    </div>
  );
}
