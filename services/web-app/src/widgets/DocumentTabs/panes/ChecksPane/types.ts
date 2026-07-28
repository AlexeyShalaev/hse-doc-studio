import type { Severity } from "@entities/checks";

// Re-export `Severity` so this module's local components keep their familiar
// import path. The canonical definition lives in @entities/checks.
export type { Severity };

export type FilterKind = "all" | "ok" | "warn" | "err" | "info" | "skipped";
export type Mode = "results" | "rules";

export type CheckItem = {
  id: string;
  sev: Severity;
  title: string;
  body: string;
  ref: string;
  line?: number;
  // Project-relative path of the file where the issue was found (from
  // location.file). Handy for prompts and for the agent's read/grep tools.
  file?: string;
  // Absolute path to the file where the issue was found. Set when the check
  // result carries a location.file — used to open the file in an external
  // editor at the right line.
  absolutePath?: string;
  // Present when sev === "skipped": why this rule was auto-suppressed
  // (the document is a custom upload, so its engine has no .tex/log to run
  // against). Rendered as dim explanatory text instead of a source location.
  skippedReason?: string;
};

export type SeverityCounts = Record<FilterKind, number>;
