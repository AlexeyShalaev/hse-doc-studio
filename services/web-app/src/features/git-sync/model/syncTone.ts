import type { SyncTone } from "./syncUi.model";

// Цвет тона: значок и подпись вместе несут смысл, цвет только подчёркивает.
export const SYNC_TONE_COLOR: Record<SyncTone, string> = {
  muted: "var(--fg-2)",
  ok: "var(--c-ok)",
  info: "var(--c-info)",
  warn: "var(--c-warn)",
  err: "var(--c-err)",
  accent: "var(--accent)",
};

export const SYNC_TONE_SOFT: Record<SyncTone, string> = {
  muted: "var(--bg-3)",
  ok: "var(--c-ok-soft)",
  info: "var(--c-info-soft)",
  warn: "var(--c-warn-soft)",
  err: "var(--c-err-soft)",
  accent: "var(--accent-soft)",
};
