import { useEffect, useMemo, useRef, useState } from "react";
import { convertFileSrc, isTauri as tauriIsTauri } from "@tauri-apps/api/core";
import { backend } from "./lib/backend";
import { formatClock, mergeSubtitleTracks } from "./lib/subtitles";
import type { SubtitleCue, TaskSummary } from "./types";

type IconName = "previous" | "next" | "play" | "pause" | "replay" | "loop";

interface StudyData {
  videoPath?: string;
  videoUrl: string;
  sourceSubtitlePath?: string;
  translatedSubtitlePath?: string;
  bilingualSubtitlePath?: string;
  cues: SubtitleCue[];
}

interface StudySessionProps {
  task: TaskSummary;
  copiedPath: string | null;
  onOpenPath(path: string): void;
  onCopyPath(path: string): void;
}

const VIDEO_EXTENSION = /\.(mp4|m4v|mov|mkv|webm|avi)(?:$|\?)/i;
const PLAYBACK_RATES = [0.75, 1, 1.25];
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

export function StudySession({ task, copiedPath, onOpenPath, onCopyPath }: StudySessionProps) {
  const videoRef = useRef<HTMLVideoElement | null>(null);
  const subtitleRefs = useRef<Record<string, HTMLButtonElement | null>>({});
  const [data, setData] = useState<StudyData | null>(null);
  const [loading, setLoading] = useState(true);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [videoError, setVideoError] = useState<string | null>(null);
  const [currentTime, setCurrentTime] = useState(0);
  const [duration, setDuration] = useState(0);
  const [paused, setPaused] = useState(true);
  const [loopCue, setLoopCue] = useState(false);
  const [playbackRate, setPlaybackRate] = useState(1);

  useEffect(() => {
    let alive = true;
    setLoading(true);
    setLoadError(null);
    setVideoError(null);
    setCurrentTime(0);
    setDuration(0);
    setPaused(true);
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
    if (videoRef.current) {
      videoRef.current.playbackRate = playbackRate;
    }
  }, [playbackRate, data?.videoUrl]);

  const cues = data?.cues ?? [];
  const activeCueIndex = useMemo(() => findNearestCueIndex(cues, currentTime), [cues, currentTime]);
  const activeCue = activeCueIndex >= 0 ? cues[activeCueIndex] : null;
  const timelineEnd = Math.max(duration || 0, cues[cues.length - 1]?.end || 0, 1);

  useEffect(() => {
    if (!activeCue) {
      return;
    }
    subtitleRefs.current[activeCue.id]?.scrollIntoView({ block: "center", behavior: "smooth" });
  }, [activeCue]);

  function seekTo(time: number) {
    const nextTime = Math.max(0, Math.min(time, timelineEnd));
    setCurrentTime(nextTime);
    if (videoRef.current) {
      videoRef.current.currentTime = nextTime;
    }
  }

  function seekToCue(index: number, shouldPlay = true) {
    const cue = cues[index];
    if (!cue) {
      return;
    }
    seekTo(cue.start + 0.02);
    if (shouldPlay && videoRef.current) {
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

  function togglePlayback() {
    if (!videoRef.current) {
      return;
    }
    if (videoRef.current.paused) {
      playVideo();
    } else {
      videoRef.current.pause();
    }
  }

  function playVideo() {
    const video = videoRef.current;
    if (!video) {
      return;
    }
    video.play().catch(() => {
      setPaused(true);
      setVideoError("视频暂时无法播放，请稍后重试。");
    });
  }

  function handleTimeUpdate(event: React.SyntheticEvent<HTMLVideoElement>) {
    const video = event.currentTarget;
    const nextTime = video.currentTime;
    if (loopCue) {
      const cueIndex = findCueIndexAtTime(cues, nextTime);
      const cue = cues[cueIndex];
      if (cue && cue.end - cue.start > 0.2 && nextTime >= cue.end - 0.06) {
        const restartTime = cue.start + 0.02;
        video.currentTime = restartTime;
        setCurrentTime(restartTime);
        return;
      }
    }
    setCurrentTime(nextTime);
  }

  if (loading) {
    return <div className="study-loading">正在打开学习视图…</div>;
  }

  if (loadError || !data) {
    return <div className="study-empty">{loadError ?? "学习视图不可用。"}</div>;
  }

  return (
    <div className="study-session">
      <div className="study-main">
        <section className="study-video-panel" aria-label="视频播放器">
          <div className="study-video-frame">
            {data.videoUrl ? (
              <video
                ref={videoRef}
                className="study-video"
                src={data.videoUrl}
                playsInline
                onLoadedMetadata={(event) => setDuration(event.currentTarget.duration || 0)}
                onTimeUpdate={handleTimeUpdate}
                onPlay={() => setPaused(false)}
                onPause={() => setPaused(true)}
                onEnded={() => setPaused(true)}
                onError={() => setVideoError("视频文件无法在当前窗口播放。")}
              />
            ) : (
              <div className="study-video-placeholder">未找到可播放的视频文件</div>
            )}
            {videoError ? <div className="study-video-error">{videoError}</div> : null}
          </div>

          <div className="study-progress-row">
            <span>{formatClock(currentTime)}</span>
            <input
              aria-label="学习进度"
              type="range"
              min="0"
              max={timelineEnd}
              step="0.05"
              value={Math.min(currentTime, timelineEnd)}
              onChange={(event) => seekTo(Number(event.currentTarget.value))}
            />
            <span>{formatClock(timelineEnd)}</span>
          </div>

          <div className="study-controls">
            <button className="icon-tool" onClick={() => skipCue(-1)} aria-label="上一句">
              <ControlIcon name="previous" />
            </button>
            <button className="icon-tool" onClick={replayCurrentCue} aria-label="重播当前句">
              <ControlIcon name="replay" />
            </button>
            <button className="play-button" onClick={togglePlayback} aria-label={paused ? "播放" : "暂停"} disabled={!data.videoUrl}>
              <ControlIcon name={paused ? "play" : "pause"} />
            </button>
            <button className="icon-tool" onClick={() => skipCue(1)} aria-label="下一句">
              <ControlIcon name="next" />
            </button>
            <button className={`loop-button ${loopCue ? "active" : ""}`} onClick={() => setLoopCue((current) => !current)}>
              <ControlIcon name="loop" />
              <span>循环当前句</span>
            </button>
            <div className="rate-control" aria-label="倍速">
              {PLAYBACK_RATES.map((rate) => (
                <button className={playbackRate === rate ? "active" : ""} key={rate} onClick={() => setPlaybackRate(rate)}>
                  {rate}x
                </button>
              ))}
            </div>
          </div>
        </section>

        <section className="subtitle-panel" aria-label="同步字幕">
          {cues.map((cue, index) => (
            <button
              className={`subtitle-card ${index === activeCueIndex ? "active" : ""}`}
              key={cue.id}
              ref={(node) => {
                subtitleRefs.current[cue.id] = node;
              }}
              onClick={() => seekToCue(index)}
            >
              <span className="subtitle-time">{formatClock(cue.start)}</span>
              <span className="subtitle-source">{cue.source}</span>
              {cue.translation ? <span className="subtitle-translation">{cue.translation}</span> : null}
            </button>
          ))}
        </section>
      </div>

      <div className="study-asset-actions">
        {data.videoPath ? <button className="mini-button" onClick={() => onOpenPath(data.videoPath!)}>定位视频</button> : null}
        {data.sourceSubtitlePath ? <button className="mini-button" onClick={() => onOpenPath(data.sourceSubtitlePath!)}>原文字幕</button> : null}
        {data.translatedSubtitlePath ? <button className="mini-button" onClick={() => onOpenPath(data.translatedSubtitlePath!)}>译文字幕</button> : null}
        {data.bilingualSubtitlePath ? <button className="mini-button" onClick={() => onOpenPath(data.bilingualSubtitlePath!)}>双语字幕</button> : null}
        {data.sourceSubtitlePath ? (
          <button className="mini-button" onClick={() => onCopyPath(data.sourceSubtitlePath!)}>
            {copiedPath === data.sourceSubtitlePath ? "已复制路径" : "复制字幕路径"}
          </button>
        ) : null}
      </div>
    </div>
  );
}
