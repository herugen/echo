import type { SubtitleCue } from "../types";

interface ParsedCue {
  index: number;
  start: number;
  end: number;
  text: string;
}

const TIMESTAMP_PATTERN = /(\d{1,2}:)?\d{1,2}:\d{2}[,.]\d{1,3}/;

function parseTimestamp(value: string): number {
  const normalized = value.trim().replace(",", ".");
  const parts = normalized.split(":");
  if (parts.length < 2) {
    return 0;
  }

  const seconds = Number(parts.pop() ?? 0);
  const minutes = Number(parts.pop() ?? 0);
  const hours = Number(parts.pop() ?? 0);
  return hours * 3600 + minutes * 60 + seconds;
}

function normalizeText(lines: string[]): string {
  return lines
    .map((line) => line.trim())
    .filter(Boolean)
    .join("\n");
}

export function parseSrt(text: string): ParsedCue[] {
  return text
    .replace(/\r/g, "")
    .split(/\n{2,}/)
    .flatMap((block, fallbackIndex) => {
      const lines = block
        .split("\n")
        .map((line) => line.trim())
        .filter(Boolean);

      if (lines.length < 2) {
        return [];
      }

      const timeLineIndex = lines.findIndex((line) => line.includes("-->") && TIMESTAMP_PATTERN.test(line));
      if (timeLineIndex === -1) {
        return [];
      }

      const [startText, endText] = lines[timeLineIndex].split("-->").map((part) => part.trim());
      const textLines = lines.slice(timeLineIndex + 1);
      const cueText = normalizeText(textLines);
      if (!cueText) {
        return [];
      }

      const rawIndex = Number(lines[0]);
      return [
        {
          index: Number.isFinite(rawIndex) ? rawIndex : fallbackIndex + 1,
          start: parseTimestamp(startText),
          end: parseTimestamp(endText),
          text: cueText,
        },
      ];
    });
}

function findMatchingCue(cues: ParsedCue[], sourceCue: ParsedCue, index: number): ParsedCue | undefined {
  const byTime = cues.find((cue) => Math.abs(cue.start - sourceCue.start) < 0.35);
  return byTime ?? cues[index];
}

function fromBilingualCue(cue: ParsedCue): SubtitleCue {
  const lines = cue.text
    .split("\n")
    .map((line) => line.trim())
    .filter(Boolean);
  const [source, ...translation] = lines;
  return {
    id: `${cue.index}-${cue.start.toFixed(2)}`,
    index: cue.index,
    start: cue.start,
    end: cue.end,
    source: source ?? cue.text,
    translation: translation.join("\n") || undefined,
  };
}

export function mergeSubtitleTracks(sourceText: string, translatedText: string, bilingualText = ""): SubtitleCue[] {
  const sourceCues = parseSrt(sourceText);
  const translatedCues = parseSrt(translatedText);

  if (!sourceCues.length && bilingualText.trim()) {
    return parseSrt(bilingualText).map(fromBilingualCue);
  }

  if (!sourceCues.length) {
    return translatedCues.map((cue) => ({
      id: `${cue.index}-${cue.start.toFixed(2)}`,
      index: cue.index,
      start: cue.start,
      end: cue.end,
      source: cue.text,
    }));
  }

  return sourceCues.map((cue, index) => {
    const translatedCue = findMatchingCue(translatedCues, cue, index);
    return {
      id: `${cue.index}-${cue.start.toFixed(2)}`,
      index: cue.index,
      start: cue.start,
      end: cue.end,
      source: cue.text,
      translation: translatedCue?.text,
    };
  });
}

export function formatClock(seconds: number): string {
  if (!Number.isFinite(seconds) || seconds < 0) {
    return "00:00";
  }

  const rounded = Math.floor(seconds);
  const hours = Math.floor(rounded / 3600);
  const minutes = Math.floor((rounded % 3600) / 60);
  const secs = rounded % 60;
  if (hours > 0) {
    return `${hours}:${String(minutes).padStart(2, "0")}:${String(secs).padStart(2, "0")}`;
  }
  return `${String(minutes).padStart(2, "0")}:${String(secs).padStart(2, "0")}`;
}
