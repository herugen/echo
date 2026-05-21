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
  const timestamp = value.match(TIMESTAMP_PATTERN)?.[0];
  if (!timestamp) {
    return 0;
  }

  const normalized = timestamp.replace(",", ".");
  const parts = normalized.split(":");
  if (parts.length < 2) {
    return 0;
  }

  const seconds = Number(parts.pop() ?? 0);
  const minutes = Number(parts.pop() ?? 0);
  const hours = Number(parts.pop() ?? 0);
  return hours * 3600 + minutes * 60 + seconds;
}

function formatVttTimestamp(seconds: number): string {
  const totalMilliseconds = Math.max(0, Math.round((Number.isFinite(seconds) ? seconds : 0) * 1000));
  const hours = Math.floor(totalMilliseconds / 3_600_000);
  const minutes = Math.floor((totalMilliseconds % 3_600_000) / 60_000);
  const wholeSeconds = Math.floor((totalMilliseconds % 60_000) / 1000);
  const milliseconds = totalMilliseconds % 1000;
  return [
    String(hours).padStart(2, "0"),
    String(minutes).padStart(2, "0"),
    `${String(wholeSeconds).padStart(2, "0")}.${String(milliseconds).padStart(3, "0")}`,
  ].join(":");
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

export function srtToWebVtt(text: string): string {
  const cues = parseSrt(text);
  if (!cues.length) {
    return "";
  }

  const blocks = cues.map((cue) => [
    `${formatVttTimestamp(cue.start)} --> ${formatVttTimestamp(cue.end)}`,
    cue.text,
  ].join("\n"));

  return ["WEBVTT", "", ...blocks].join("\n\n");
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

function normalizeInlineText(text: string): string {
  return text.replace(/\s*\n+\s*/g, " ").replace(/\s+/g, " ").trim();
}

function joinTextParts(parts: string[]): string {
  return parts
    .map((part) => part.trim())
    .filter(Boolean)
    .reduce((joined, part) => {
      if (!joined) {
        return part;
      }
      const needsSpace = !/[\u4e00-\u9fff]$/.test(joined) && !/^[\u4e00-\u9fff]/.test(part);
      return `${joined}${needsSpace ? " " : ""}${part}`.trim();
    }, "");
}

function shouldSplitCue(cue: SubtitleCue): boolean {
  const duration = cue.end - cue.start;
  return duration > LONG_CUE_SECONDS || cue.source.length > LONG_SOURCE_TEXT || textLength(cue.translation) > LONG_TRANSLATED_TEXT;
}

function splitText(text: string, targetLength: number): string[] {
  const normalized = normalizeInlineText(text);
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

function combineTextParts(parts: string[], targetCount: number): string[] {
  if (parts.length <= targetCount) {
    return parts;
  }

  const totalLength = parts.reduce((total, part) => total + textLength(part), 0);
  const targetLength = Math.max(totalLength / targetCount, 1);
  const combined: string[] = [];
  let bucket: string[] = [];
  let bucketLength = 0;

  parts.forEach((part, index) => {
    const remainingParts = parts.length - index;
    const remainingBuckets = targetCount - combined.length;
    const shouldFlush =
      bucket.length > 0 &&
      combined.length < targetCount - 1 &&
      bucketLength + textLength(part) > targetLength &&
      remainingParts >= remainingBuckets;

    if (shouldFlush) {
      combined.push(joinTextParts(bucket));
      bucket = [];
      bucketLength = 0;
    }

    bucket.push(part);
    bucketLength += textLength(part);
  });

  if (bucket.length) {
    combined.push(joinTextParts(bucket));
  }

  while (combined.length > targetCount) {
    const tail = combined.pop();
    if (!tail) {
      break;
    }
    combined[combined.length - 1] = joinTextParts([combined[combined.length - 1], tail]);
  }

  return combined;
}

function splitTextPartOnce(part: string): [string, string] | null {
  const normalized = normalizeInlineText(part);
  if (normalized.length < 2) {
    return null;
  }

  const middle = normalized.length / 2;
  const strongCandidates: number[] = [];
  const softCandidates: number[] = [];
  const spaceCandidates: number[] = [];
  for (let index = 1; index < normalized.length; index += 1) {
    const previous = normalized[index - 1];
    const current = normalized[index];
    if (/[.!?。！？]/.test(previous)) {
      strongCandidates.push(index);
    } else if (/[,;:，、；：]/.test(previous)) {
      softCandidates.push(index);
    } else if (/\s/.test(current) || /\s/.test(previous)) {
      spaceCandidates.push(index);
    }
  }

  const lowerBound = Math.max(1, Math.floor(normalized.length * 0.2));
  const upperBound = Math.min(normalized.length - 1, Math.ceil(normalized.length * 0.8));
  const nearestMiddleCandidate = (candidates: number[]) =>
    candidates
      .filter((candidate) => candidate >= lowerBound && candidate <= upperBound)
      .sort((left, right) => Math.abs(left - middle) - Math.abs(right - middle))[0];
  const splitIndex =
    nearestMiddleCandidate(strongCandidates) ??
    nearestMiddleCandidate(softCandidates) ??
    nearestMiddleCandidate(spaceCandidates) ??
    Math.floor(middle);

  const left = normalized.slice(0, splitIndex).trim();
  const right = normalized.slice(splitIndex).trim();
  return left && right ? [left, right] : null;
}

function resizeTextParts(text: string | undefined, parts: string[], targetCount: number): string[] {
  const normalized = normalizeInlineText(text ?? "");
  if (!normalized) {
    return [];
  }

  let resized = parts.length ? parts : [normalized];
  resized = resized.map((part) => normalizeInlineText(part)).filter(Boolean);

  if (resized.length > targetCount) {
    resized = combineTextParts(resized, targetCount);
  }

  while (resized.length < targetCount) {
    const splitIndex = resized
      .map((part, index) => ({ index, length: textLength(part) }))
      .sort((left, right) => right.length - left.length)[0]?.index;
    if (splitIndex === undefined) {
      break;
    }

    const split = splitTextPartOnce(resized[splitIndex]);
    if (!split) {
      break;
    }
    resized.splice(splitIndex, 1, ...split);
  }

  return resized;
}

function splitCue(cue: SubtitleCue): SubtitleCue[] {
  if (!shouldSplitCue(cue)) {
    return [cue];
  }

  const initialSourceParts = splitText(cue.source, 120);
  const initialTranslationParts = cue.translation ? splitText(cue.translation, 72) : [];
  const partCount = Math.max(initialSourceParts.length, initialTranslationParts.length, 1);
  if (partCount <= 1) {
    return [cue];
  }

  const sourceParts = resizeTextParts(cue.source, initialSourceParts, partCount);
  const translationParts = resizeTextParts(cue.translation, initialTranslationParts, partCount);
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
    const translation = cue.translation ? translationParts[index] ?? translationParts[translationParts.length - 1] ?? cue.translation : undefined;
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
