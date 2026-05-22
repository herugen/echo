export type TaskStatus = "draft" | "running" | "failed" | "succeeded" | "cancelled" | "paused";

export interface AppSettings {
  outputDir: string;
  translatorBackend: string;
  deepseekBaseUrl: string;
  deepseekApiKey: string;
}

export interface StageSummary {
  name: string;
  status: string;
  detail?: string;
  artifacts: string[];
}

export interface TaskSummary {
  id: string;
  title: string;
  status: TaskStatus;
  stageLabel: string;
  detail: string;
  outputDir?: string;
  assetDir: string;
  progress: number;
  stages?: StageSummary[];
  sourceLabel?: string;
  description?: string;
  durationSeconds?: number;
  durationLabel?: string;
  addedLabel?: string;
  resolutionLabel?: string;
  thumbnailKind?: string;
}

export interface SubtitleCue {
  id: string;
  index: number;
  start: number;
  end: number;
  source: string;
  translation?: string;
}
