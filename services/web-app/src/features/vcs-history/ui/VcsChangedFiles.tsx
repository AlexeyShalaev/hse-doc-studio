import { type ReactNode, useMemo, useState } from "react";
import { useTranslation } from "react-i18next";
import {
  ChevronRight,
  FileText,
  Folder,
  FolderTree,
  List,
  Search,
  X,
} from "lucide-react";
import { clsx } from "clsx";
import type { VcsFileDiff } from "@entities/vcs";
import {
  type DiffFileNode,
  type DiffStat,
  buildFileTree,
  changeMeta,
  collectDirPaths,
  sortedChildren,
} from "./vcsDiff.model";

// File browser for a diff: search box + tree/list toggle. Each row shows the
// change status (colour-coded letter) and ±counts; clicking selects the file.

export type VcsChangedFilesProps = {
  files: VcsFileDiff[];
  stats: Map<string, DiffStat>;
  activePath: string | null;
  onSelect: (path: string) => void;
  maxHeight?: number;
};

type ViewMode = "tree" | "list";

export const VcsChangedFiles = ({
  files,
  stats,
  activePath,
  onSelect,
  maxHeight = 220,
}: VcsChangedFilesProps) => {
  const { t } = useTranslation("vcsHistory");
  const [query, setQuery] = useState("");
  const [view, setView] = useState<ViewMode>("tree");
  const [collapsed, setCollapsed] = useState<Set<string>>(new Set());

  const trimmed = query.trim().toLowerCase();
  const filtered = useMemo(
    () =>
      trimmed
        ? files.filter((f) => f.path.toLowerCase().includes(trimmed))
        : files,
    [files, trimmed],
  );

  const tree = useMemo(() => buildFileTree(filtered), [filtered]);
  // While searching, force every directory open so matches are visible.
  const effectiveCollapsed = trimmed ? new Set<string>() : collapsed;

  const fileRow = (
    file: VcsFileDiff,
    label: string,
    depth: number,
  ): ReactNode => {
    const meta = changeMeta(file.change);
    const stat = stats.get(file.path) ?? { add: 0, del: 0 };
    const isActive = activePath === file.path;
    return (
      <button
        key={`f:${file.path}`}
        type="button"
        className={clsx("vcs-file-row", isActive && "active")}
        style={{ paddingLeft: 8 + depth * 14 }}
        onClick={() => {
          onSelect(file.path);
        }}
        title={file.path}
      >
        <span
          className="mono"
          style={{
            flexShrink: 0,
            width: 13,
            textAlign: "center",
            fontWeight: 700,
            color: meta.color,
          }}
        >
          {meta.letter}
        </span>
        <FileText size={12} style={{ flexShrink: 0, color: "var(--fg-3)" }} />
        <span className="truncate" style={{ flex: 1 }}>
          {label}
        </span>
        {!file.binary && (stat.add > 0 || stat.del > 0) && (
          <span
            className="mono"
            style={{ flexShrink: 0, display: "flex", gap: 5, fontSize: 9.5 }}
          >
            {stat.add > 0 && (
              <span style={{ color: "var(--c-ok)" }}>+{String(stat.add)}</span>
            )}
            {stat.del > 0 && (
              <span style={{ color: "var(--c-err)" }}>−{String(stat.del)}</span>
            )}
          </span>
        )}
      </button>
    );
  };

  const renderNode = (node: DiffFileNode, depth: number): ReactNode[] => {
    const rows: ReactNode[] = [];
    for (const child of sortedChildren(node)) {
      const isDir = child.children.size > 0;
      if (isDir) {
        const isOpen = !effectiveCollapsed.has(child.path);
        rows.push(
          <button
            key={`d:${child.path}`}
            type="button"
            className="vcs-file-row vcs-dir-row"
            style={{ paddingLeft: 8 + depth * 14 }}
            onClick={() => {
              setCollapsed((prev) => {
                const next = new Set(prev);
                if (next.has(child.path)) next.delete(child.path);
                else next.add(child.path);
                return next;
              });
            }}
            title={child.path}
          >
            <ChevronRight
              size={12}
              style={{
                flexShrink: 0,
                color: "var(--fg-3)",
                transform: isOpen ? "rotate(90deg)" : undefined,
                transition: "transform 0.1s",
              }}
            />
            <Folder size={12} style={{ flexShrink: 0, color: "var(--fg-3)" }} />
            <span className="truncate" style={{ flex: 1 }}>
              {child.name}
            </span>
          </button>,
        );
        if (isOpen) rows.push(...renderNode(child, depth + 1));
      } else if (child.file) {
        rows.push(fileRow(child.file, child.name, depth));
      }
    }
    return rows;
  };

  const dirCount = useMemo(() => collectDirPaths(tree).size, [tree]);
  // A flat tree (no nested folders) — list view is the only sensible one.
  const canTree = dirCount > 0;
  const showTree = view === "tree" && canTree;

  return (
    <div className="card" style={{ overflow: "hidden" }}>
      <div
        className="flex items-center"
        style={{
          gap: 6,
          padding: "6px 8px",
          borderBottom: "1px solid var(--border)",
        }}
      >
        <div
          className="flex items-center"
          style={{ position: "relative", flex: 1 }}
        >
          <Search
            size={12}
            style={{
              position: "absolute",
              left: 8,
              color: "var(--fg-3)",
              pointerEvents: "none",
            }}
          />
          <input
            className="input mono"
            style={{
              fontSize: 11,
              padding: "5px 24px 5px 26px",
              height: 28,
            }}
            placeholder={t("changedFiles.searchPlaceholder")}
            value={query}
            onChange={(e) => {
              setQuery(e.target.value);
            }}
          />
          {query && (
            <button
              type="button"
              className="icon-btn sm"
              style={{ position: "absolute", right: 2 }}
              onClick={() => {
                setQuery("");
              }}
              title={t("changedFiles.clear")}
            >
              <X size={12} />
            </button>
          )}
        </div>
        {canTree && (
          <div className="flex items-center" style={{ gap: 2 }}>
            <button
              type="button"
              className={clsx("icon-btn sm", showTree && "active")}
              onClick={() => {
                setView("tree");
              }}
              title={t("changedFiles.viewTree")}
            >
              <FolderTree size={13} />
            </button>
            <button
              type="button"
              className={clsx("icon-btn sm", !showTree && "active")}
              onClick={() => {
                setView("list");
              }}
              title={t("changedFiles.viewList")}
            >
              <List size={13} />
            </button>
          </div>
        )}
      </div>

      <div style={{ maxHeight, overflowY: "auto" }}>
        {filtered.length === 0 ? (
          <div
            className="dim"
            style={{ padding: 14, fontSize: 11.5, textAlign: "center" }}
          >
            {t("changedFiles.empty")}
          </div>
        ) : showTree ? (
          renderNode(tree, 0)
        ) : (
          filtered.map((file) => fileRow(file, file.path, 0))
        )}
      </div>
    </div>
  );
};
