import { i18n } from "@shared/lib/i18n";

// Pure helpers for rendering a unified diff: change metadata, +/- counting and a
// small unified-diff parser (the backend gives raw per-file patch text). Shared
// by the version history, the template update and the git conflict screens. No
// React here.

export type DiffChangeMeta = {
  label: string;
  letter: string;
  color: string;
  soft: string;
};

const CHANGE_META: Record<
  string,
  Omit<DiffChangeMeta, "label"> & { labelKey: string }
> = {
  A: {
    labelKey: "diffPatch.change.added",
    letter: "A",
    color: "var(--c-ok)",
    soft: "var(--c-ok-soft)",
  },
  M: {
    labelKey: "diffPatch.change.modified",
    letter: "M",
    color: "var(--c-warn)",
    soft: "var(--c-warn-soft)",
  },
  D: {
    labelKey: "diffPatch.change.deleted",
    letter: "D",
    color: "var(--c-err)",
    soft: "var(--c-err-soft)",
  },
  R: {
    labelKey: "diffPatch.change.renamed",
    letter: "R",
    color: "var(--c-info)",
    soft: "var(--c-info-soft)",
  },
  C: {
    labelKey: "diffPatch.change.copied",
    letter: "C",
    color: "var(--c-info)",
    soft: "var(--c-info-soft)",
  },
};

export const changeMeta = (change: string): DiffChangeMeta => {
  const meta = CHANGE_META[change];
  if (meta) {
    const { labelKey, ...rest } = meta;
    return { ...rest, label: i18n.t(`uiPrimitives:${labelKey}`) };
  }
  return {
    label: change,
    letter: change.slice(0, 1) || "?",
    color: "var(--fg-2)",
    soft: "var(--bg-2)",
  };
};

export type DiffStat = { add: number; del: number };

export const countChanges = (patch: string): DiffStat => {
  let add = 0;
  let del = 0;
  for (const line of patch.split("\n")) {
    if (line.startsWith("+") && !line.startsWith("+++")) add += 1;
    else if (line.startsWith("-") && !line.startsWith("---")) del += 1;
  }
  return { add, del };
};

export type PatchLineKind = "context" | "add" | "del" | "meta";

export type ParsedDiffLine = {
  kind: PatchLineKind;
  text: string;
  oldNo: number | null;
  newNo: number | null;
};

export type ParsedHunk = { header: string; lines: ParsedDiffLine[] };

const HUNK_RE = /^@@ -(\d+)(?:,\d+)? \+(\d+)(?:,\d+)? @@/;

// Turn a raw unified-diff patch into hunks with per-line old/new numbers. File
// headers (diff --git / index / --- / +++) are skipped — the UI shows its own.
export const parsePatch = (patch: string): ParsedHunk[] => {
  const hunks: ParsedHunk[] = [];
  let current: ParsedHunk | null = null;
  let oldNo = 0;
  let newNo = 0;
  for (const raw of patch.split("\n")) {
    const m = HUNK_RE.exec(raw);
    if (m) {
      oldNo = Number(m[1]);
      newNo = Number(m[2]);
      current = { header: raw, lines: [] };
      hunks.push(current);
      continue;
    }
    if (!current) continue;
    const head = raw[0];
    if (head === "+") {
      current.lines.push({
        kind: "add",
        text: raw.slice(1),
        oldNo: null,
        newNo,
      });
      newNo += 1;
    } else if (head === "-") {
      current.lines.push({
        kind: "del",
        text: raw.slice(1),
        oldNo,
        newNo: null,
      });
      oldNo += 1;
    } else if (head === "\\") {
      current.lines.push({ kind: "meta", text: raw, oldNo: null, newNo: null });
    } else {
      current.lines.push({
        kind: "context",
        text: raw.startsWith(" ") ? raw.slice(1) : raw,
        oldNo,
        newNo,
      });
      oldNo += 1;
      newNo += 1;
    }
  }
  return hunks;
};
