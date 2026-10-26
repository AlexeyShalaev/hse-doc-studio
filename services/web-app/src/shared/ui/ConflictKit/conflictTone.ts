// Tone map shared by every conflict / merge screen: red means the decision is
// the user's, amber means the user's edits take part, green is something new,
// muted is a silent update.

export type ConflictTone = "err" | "warn" | "ok" | "info" | "muted";

const TONE_COLOR: Record<ConflictTone, string> = {
  err: "var(--c-err)",
  warn: "var(--c-warn)",
  ok: "var(--c-ok)",
  info: "var(--c-info)",
  muted: "var(--fg-2)",
};

const TONE_SOFT: Record<ConflictTone, string> = {
  err: "var(--c-err-soft)",
  warn: "var(--c-warn-soft)",
  ok: "var(--c-ok-soft)",
  info: "var(--c-info-soft)",
  muted: "var(--bg-2)",
};

export const toneColor = (tone: ConflictTone): string => TONE_COLOR[tone];

export const toneSoft = (tone: ConflictTone): string => TONE_SOFT[tone];
