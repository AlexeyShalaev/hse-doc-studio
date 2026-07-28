import type { FileTreeItemResponse } from "@shared/api/types";
import { isHiddenDirPath, isHiddenPath, isReadOnlyPath } from "./fileFilters";

export type FileNode = {
  name: string;
  /** Full project-relative POSIX path. */
  path: string;
  type: "file" | "folder";
  children?: FileNode[];
  size?: number;
  modifiedAt?: string;
  isHidden: boolean;
  isReadOnly: boolean;
  /** Template-origin files (and folders containing only them) can't be deleted. */
  deletable: boolean;
};

type MutableNode = {
  name: string;
  path: string;
  type: "file" | "folder";
  size?: number;
  modifiedAt?: string;
  isHidden?: boolean;
  isReadOnly?: boolean;
  deletable?: boolean;
  children: Map<string, MutableNode>;
};

const makeFolder = (name: string, path: string): MutableNode => ({
  name,
  path,
  type: "folder",
  isHidden: path === "" ? false : isHiddenDirPath(path),
  children: new Map(),
});

const finalize = (node: MutableNode): FileNode => {
  if (node.type === "file") {
    return {
      name: node.name,
      path: node.path,
      type: "file",
      isHidden: node.isHidden ?? false,
      isReadOnly: node.isReadOnly ?? false,
      deletable: node.deletable ?? true,
      ...(node.size !== undefined ? { size: node.size } : {}),
      ...(node.modifiedAt !== undefined ? { modifiedAt: node.modifiedAt } : {}),
    };
  }
  const children = [...node.children.values()].map(finalize);
  children.sort((a, b) => {
    if (a.type !== b.type) return a.type === "folder" ? -1 : 1;
    return a.name.localeCompare(b.name, "ru", { sensitivity: "base" });
  });
  return {
    name: node.name,
    path: node.path,
    type: "folder",
    isHidden: node.isHidden ?? false,
    isReadOnly: false,
    // A folder with files is deletable only if every file under it is user-added
    // (one template file protects the whole folder). An empty folder has no
    // children, so it falls back to its own entry's flag (user dirs → true).
    deletable:
      children.length > 0
        ? children.every((c) => c.deletable)
        : (node.deletable ?? true),
    children,
  };
};

/**
 * Folds the backend's flat list of `{ path, size, modified_at }` into a nested,
 * sorted (folders-first) tree. Artifact/generated paths are dropped unless
 * `includeHidden` is set, in which case they're flagged `isHidden` for greying.
 */
export const buildFileTree = (
  items: readonly FileTreeItemResponse[],
  includeHidden = false,
): FileNode[] => {
  const root = makeFolder("", "");

  for (const item of items) {
    const hidden = isHiddenPath(item.path);
    if (hidden && !includeHidden) continue;

    const segments = item.path.split("/").filter(Boolean);
    if (segments.length === 0) continue;

    let cursor = root;
    let prefix = "";
    segments.forEach((segment, index) => {
      prefix = prefix ? `${prefix}/${segment}` : segment;
      const isLeaf = index === segments.length - 1;
      let node = cursor.children.get(segment);
      if (!node) {
        node =
          isLeaf && !item.is_dir
            ? {
                name: segment,
                path: prefix,
                type: "file",
                size: item.size,
                modifiedAt: item.modified_at,
                isHidden: hidden,
                isReadOnly: isReadOnlyPath(prefix),
                deletable: item.deletable,
                children: new Map(),
              }
            : makeFolder(segment, prefix);
        cursor.children.set(segment, node);
      }
      // An explicit directory entry records the folder's own deletable flag so
      // empty user folders (no children) remain deletable.
      if (isLeaf && item.is_dir && node.type === "folder") {
        node.deletable = item.deletable;
        if (hidden) node.isHidden = true;
      }
      cursor = node;
    });
  }

  return finalize(root).children ?? [];
};

/** Folder paths on the way to `path` (for auto-expanding the tree to a file). */
export const ancestorFolders = (path: string): string[] => {
  const segments = path.split("/").filter(Boolean);
  const out: string[] = [];
  let prefix = "";
  segments.slice(0, -1).forEach((segment) => {
    prefix = prefix ? `${prefix}/${segment}` : segment;
    out.push(prefix);
  });
  return out;
};
