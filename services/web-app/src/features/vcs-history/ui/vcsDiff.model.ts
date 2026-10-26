import type { VcsFileDiff } from "@entities/vcs";

// Pure helpers for the diff browser's file tree. The per-file patch parsing and
// ±counting live in shared/ui/DiffPatch (also used by template update). No
// React here.

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
