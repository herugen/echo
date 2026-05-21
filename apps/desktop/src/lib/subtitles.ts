import type { SubtitleCue } from "../types";

interface ParsedCue {
  index: number;
  start: number;
  end: number;
  text: string;
}

const TIMESTAMP_PATTERN = /(\d{1,2}:)?\d{1,2}:\d{2}[,.]\d{1,3}/;
const LONG_SOURCE_TEXT = 150;
const LONG_TRANSLATED_TEXT = 90;
const LONG_CUE_SECONDS = 9;
const SENTENCE_BOUNDARY = /(?<=[.!?;。！？；])\s+/;
const SOFT_ENGLISH_BOUNDARY = /(?<=,)\s+|(?=\b(?:so|but|and|then|because|basically|which|that|when|where|now|this|you|we|i)\b)/i;
const SOFT_CJK_BOUNDARY = /(?<=[，、：])|(?=所以|然后|但是|因为|那么|这个|那个|我们|你们|他们|它们)/;

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

function textLength(value = ""): number {
  return value.replace(/\s+/g, "").length;
}

function shouldSplitCue(cue: SubtitleCue): boolean {
  const duration = cue.end - cue.start;
  return duration > LONG_CUE_SECONDS || cue.source.length > LONG_SOURCE_TEXT || textLength(cue.translation) > LONG_TRANSLATED_TEXT;
}

function splitText(text: string, targetLength: number): string[] {
  const normalized = text.replace(/\s*\n+\s*/g, " ").replace(/\s+/g, " ").trim();
  if (!normalized || normalized.length <= targetLength) {
    return normalized ? [normalized] : [];
  }

  const primaryParts = normalized.split(SENTENCE_BOUNDARY).filter(Boolean);
  const sentenceParts = primaryParts.length > 1 ? primaryParts : normalized.split(SOFT_ENGLISH_BOUNDARY).filter(Boolean);
  const rawParts = sentenceParts.length > 1 ? sentenceParts : normalized.split(SOFT_CJK_BOUNDARY).filter(Boolean);
  const parts = rawParts.length > 1 ? rawParts : normalized.match(new RegExp(`.{1,${targetLength}}`, "g")) ?? [normalized];
  const chunks: string[] = [];

  for (const part of parts.map((item) => item.trim()).filter(Boolean)) {
    const last = chunks[chunks.length - 1];
    if (last && last.length + part.length + 1 <= targetLength) {
      const needsSpace = !/[\u4e00-\u9fff]$/.test(last) && !/^[\u4e00-\u9fff]/.test(part);
      chunks[chunks.length - 1] = `${last}${needsSpace ? " " : ""}${part}`.trim();
    } else if (part.length > targetLength * 1.35) {
      chunks.push(...(part.match(new RegExp(`.{1,${targetLength}}`, "g")) ?? [part]));
    } else {
      chunks.push(part);
    }
  }

  return chunks;
}

function splitCue(cue: SubtitleCue): SubtitleCue[] {
  if (!shouldSplitCue(cue)) {
    return [cue];
  }

  const sourceParts = splitText(cue.source, 120);
  const translationParts = cue.translation ? splitText(cue.translation, 72) : [];
  const partCount = Math.max(sourceParts.length, translationParts.length, 1);
  if (partCount <= 1) {
    return [cue];
  }

  const duration = Math.max(cue.end - cue.start, 0.35);
  const weights = Array.from({ length: partCount }, (_, index) => {
    const sourceWeight = textLength(sourceParts[index]);
    const translationWeight = textLength(translationParts[index]);
    return Math.max(sourceWeight, translationWeight, 1);
  });
  const totalWeight = weights.reduce((total, weight) => total + weight, 0);

  let elapsedWeight = 0;
  return Array.from({ length: partCount }, (_, index) => {
    const source = sourceParts[index] ?? sourceParts[sourceParts.length - 1] ?? cue.source;
    const translation = translationParts[index] ?? (index === 0 ? cue.translation : undefined);
    const isLast = index === partCount - 1;
    const start = cue.start + (duration * elapsedWeight) / totalWeight;
    elapsedWeight += weights[index];
    const end = isLast ? cue.end : cue.start + (duration * elapsedWeight) / totalWeight;
    return {
      ...cue,
      id: `${cue.id}-${index + 1}`,
      index: cue.index + index / 100,
      start,
      end: Math.max(end, start + 0.1),
      source,
      translation,
    };
  });
}

function splitLongCues(cues: SubtitleCue[]): SubtitleCue[] {
  return cues.flatMap(splitCue);
}

export function mergeSubtitleTracks(sourceText: string, translatedText: string, bilingualText = ""): SubtitleCue[] {
  const sourceCues = parseSrt(sourceText);
  const translatedCues = parseSrt(translatedText);

  if (!sourceCues.length && bilingualText.trim()) {
    return splitLongCues(parseSrt(bilingualText).map(fromBilingualCue));
  }

  if (!sourceCues.length) {
    return splitLongCues(translatedCues.map((cue) => ({
      id: `${cue.index}-${cue.start.toFixed(2)}`,
      index: cue.index,
      start: cue.start,
      end: cue.end,
      source: cue.text,
    })));
  }

  return splitLongCues(sourceCues.map((cue, index) => {
    const translatedCue = findMatchingCue(translatedCues, cue, index);
    return {
      id: `${cue.index}-${cue.start.toFixed(2)}`,
      index: cue.index,
      start: cue.start,
      end: cue.end,
      source: cue.text,
      translation: translatedCue?.text,
    };
  }));
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
