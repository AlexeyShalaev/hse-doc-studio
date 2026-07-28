import { i18n } from "@shared/lib";
import type { VcsFileDiff } from "@entities/vcs";

// Pure helpers for the diff browser: change metadata, +/- counting, a small
// unified-diff parser (the backend gives raw per-file patch text), and a
// file-path tree builder. No React here.

export type VcsChangeMeta = {
  label: string;
  letter: string;
  color: string;
  soft: string;
};

const CHANGE_META: Record<
  string,
  Omit<VcsChangeMeta, "label"> & { labelKey: string }
> = {
  A: {
    labelKey: "change.added",
    letter: "A",
    color: "var(--c-ok)",
    soft: "var(--c-ok-soft)",
  },
  M: {
    labelKey: "change.modified",
    letter: "M",
    color: "var(--c-warn)",
    soft: "var(--c-warn-soft)",
  },
  D: {
    labelKey: "change.deleted",
    letter: "D",
    color: "var(--c-err)",
    soft: "var(--c-err-soft)",
  },
  R: {
    labelKey: "change.renamed",
    letter: "R",
    color: "var(--c-info)",
    soft: "var(--c-info-soft)",
  },
  C: {
    labelKey: "change.copied",
    letter: "C",
    color: "var(--c-info)",
    soft: "var(--c-info-soft)",
  },
};

export const changeMeta = (change: string): VcsChangeMeta => {
  const meta = CHANGE_META[change];
  if (meta) {
    const { labelKey, ...rest } = meta;
    return { ...rest, label: i18n.t(`vcsHistory:${labelKey}`) };
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

export type DiffLineKind = "context" | "add" | "del" | "meta";

export type ParsedDiffLine = {
  kind: DiffLineKind;
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

export type DiffFileNode = {
  name: string;
  path: string;
  file?: VcsFileDiff;
  children: Map<string, DiffFileNode>;
};

export const buildFileTree = (files: VcsFileDiff[]): DiffFileNode => {
  const root: DiffFileNode = { name: "", path: "", children: new Map() };
  for (const file of files) {
    const parts = file.path.split("/");
    let node = root;
    parts.forEach((part, i) => {
      const path = parts.slice(0, i + 1).join("/");
      let child = node.children.get(part);
      if (!child) {
        child = { name: part, path, children: new Map() };
        node.children.set(part, child);
      }
      node = child;
    });
    node.file = file;
  }
  return root;
};

// Children sorted directories-first, then alphabetically.
export const sortedChildren = (node: DiffFileNode): DiffFileNode[] =>
  [...node.children.values()].sort((a, b) => {
    const aDir = a.children.size > 0 ? 0 : 1;
    const bDir = b.children.size > 0 ? 0 : 1;
    if (aDir !== bDir) return aDir - bDir;
    return a.name.localeCompare(b.name, "ru");
  });

export const collectDirPaths = (
  node: DiffFileNode,
  acc: Set<string> = new Set(),
): Set<string> => {
  node.children.forEach((child) => {
    if (child.children.size > 0) {
      acc.add(child.path);
      collectDirPaths(child, acc);
    }
  });
  return acc;
};
