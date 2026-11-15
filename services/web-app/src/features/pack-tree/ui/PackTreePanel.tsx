import { useMemo, useState } from "react";
import {
  ChevronDown,
  ChevronRight,
  FileCode2,
  FileText,
  Folder,
  Lock,
  Package,
  RefreshCw,
} from "lucide-react";
import { clsx } from "clsx";
import { useTranslation } from "react-i18next";
import {
  ancestorsOf,
  buildFileTree,
  isTextPath,
  packErrorText,
  usePackTree,
  type PackReadOnlyReason,
  type PackTree,
  type PackTreeNode,
  type PackTreeVersion,
} from "@entities/pack-studio";
import { pickLocalized } from "@shared/lib";
import { ErrorState, Spinner } from "@shared/ui";
import { Notice } from "@shared/ui/ConflictKit";
import { versionStatusVariant } from "../lib/versionBadge";

export type PackTreePanelProps = {
  workspaceId: string;
  selectedPath: string | null;
  onSelect: (path: string) => void;
};

type Annotations = {
  versions: Map<string, PackTreeVersion>;
  names: Map<string, string>;
};

/** Версии и подписи паков и шаблонов по пути каталога (в нижнем регистре). */
const annotate = (tree: PackTree, lang: string): Annotations => {
  const versions = new Map<string, PackTreeVersion>();
  const names = new Map<string, string>();
  for (const pack of tree.packs) {
    if (pack.name) {
      names.set(
        pack.path.toLowerCase(),
        pickLocalized(pack.name, lang, pack.id),
      );
    }
    for (const template of pack.templates) {
      if (template.name) {
        names.set(
          template.path.toLowerCase(),
          pickLocalized(template.name, lang, template.id),
        );
      }
      for (const version of template.versions) {
        versions.set(version.path.toLowerCase(), version);
      }
    }
  }
  return { versions, names };
};

const withItem = (
  set: ReadonlySet<string>,
  item: string,
  present: boolean,
): ReadonlySet<string> => {
  if (set.has(item) === present) return set;
  const next = new Set(set);
  if (present) next.add(item);
  else next.delete(item);
  return next;
};

const READ_ONLY_KEY: Record<PackReadOnlyReason, string> = {
  version_released: "tree.readOnly.versionReleased",
  releases_read_only: "tree.readOnly.releasesRegistry",
};

const VersionMarks = ({ version }: { version: PackTreeVersion }) => {
  const { t } = useTranslation("packStudio");
  return (
    <span className="ps-tree-marks">
      {version.status && (
        <span
          className={clsx(
            "ps-mark",
            `ps-mark-${versionStatusVariant(version.status)}`,
          )}
        >
          {version.status}
        </span>
      )}
      {version.released && (
        <span
          className="ps-mark ps-mark-lock"
          title={t("tree.released")}
          aria-label={t("tree.released")}
          data-testid={`tree-released-${version.version}`}
        >
          <Lock size="0.625rem" aria-hidden="true" />
        </span>
      )}
      {version.modified && (
        <span
          className="ps-mark ps-mark-warn"
          title={t("tree.modifiedHint")}
          data-testid={`tree-modified-${version.version}`}
        >
          {t("tree.modified")}
        </span>
      )}
    </span>
  );
};

type NodeProps = {
  node: PackTreeNode;
  depth: number;
  open: ReadonlySet<string>;
  toggle: (path: string) => void;
  selectedPath: string | null;
  onSelect: (path: string) => void;
  notes: Annotations;
};

const TreeNode = ({
  node,
  depth,
  open,
  toggle,
  selectedPath,
  onSelect,
  notes,
}: NodeProps) => {
  const { t } = useTranslation("packStudio");
  const key = node.path.toLowerCase();
  const indent = { paddingLeft: `${String(0.5 + depth * 0.875)}rem` };
  if (node.isDir) {
    const expanded = open.has(node.path);
    const version = notes.versions.get(key);
    const name = notes.names.get(key);
    const Chevron = expanded ? ChevronDown : ChevronRight;
    const Icon = depth === 0 ? Package : Folder;
    return (
      <li role="treeitem" aria-expanded={expanded} aria-selected={false}>
        <button
          type="button"
          className="ps-tree-row"
          style={indent}
          onClick={() => {
            toggle(node.path);
          }}
          data-testid={`tree-dir-${node.path}`}
        >
          <Chevron
            size="0.75rem"
            aria-hidden="true"
            className="ps-tree-chevron"
          />
          <Icon size="0.8125rem" aria-hidden="true" className="ps-tree-icon" />
          <span className="ps-tree-name truncate">{node.name}</span>
          {name && <span className="ps-tree-hint truncate">{name}</span>}
          {version && <VersionMarks version={version} />}
        </button>
        {expanded && node.children.length > 0 && (
          <ul role="group" className="ps-tree-group">
            {node.children.map((child) => (
              <TreeNode
                key={child.path}
                node={child}
                depth={depth + 1}
                open={open}
                toggle={toggle}
                selectedPath={selectedPath}
                onSelect={onSelect}
                notes={notes}
              />
            ))}
          </ul>
        )}
      </li>
    );
  }
  const text = isTextPath(node.path);
  const selected = node.path === selectedPath;
  const Icon = node.name.endsWith(".j2") ? FileCode2 : FileText;
  const readOnlyLabel = node.readOnly ? t(READ_ONLY_KEY[node.readOnly]) : null;
  return (
    <li role="treeitem" aria-selected={selected}>
      <button
        type="button"
        className={clsx("ps-tree-row", selected && "active")}
        style={indent}
        disabled={!text}
        title={text ? (readOnlyLabel ?? node.path) : t("tree.binary")}
        onClick={() => {
          onSelect(node.path);
        }}
        data-testid={`tree-file-${node.path}`}
      >
        <span className="ps-tree-chevron" aria-hidden="true" />
        <Icon size="0.8125rem" aria-hidden="true" className="ps-tree-icon" />
        <span className="ps-tree-name truncate">{node.name}</span>
        {readOnlyLabel && (
          <span className="ps-mark ps-mark-lock" aria-label={readOnlyLabel}>
            <Lock size="0.625rem" aria-hidden="true" />
          </span>
        )}
      </button>
    </li>
  );
};

/**
 * Дерево рабочего пространства: паки, шаблоны, версии со статусом, замком у
 * выпущенных и пометкой «изменена» у правленных мимо Студии; файлы, которые
 * менять нельзя, с замком. Картинки и шрифты в редакторе не открываются.
 */
export const PackTreePanel = ({
  workspaceId,
  selectedPath,
  onSelect,
}: PackTreePanelProps) => {
  const { t, i18n } = useTranslation("packStudio");
  const tree = usePackTree(workspaceId);
  const nodes = useMemo(
    () => (tree.data ? buildFileTree(tree.data.files) : []),
    [tree.data],
  );
  const notes = useMemo(
    (): Annotations =>
      tree.data
        ? annotate(tree.data, i18n.language)
        : { versions: new Map(), names: new Map() },
    [tree.data, i18n.language],
  );
  // Раскрытые папки: по умолчанию паки и путь к открытому файлу, поверх них
  // то, что человек раскрыл или свернул сам.
  const [opened, setOpened] = useState<ReadonlySet<string>>(() => new Set());
  const [closed, setClosed] = useState<ReadonlySet<string>>(() => new Set());
  const open = useMemo(() => {
    const result = new Set<string>(nodes.map((node) => node.path));
    if (selectedPath) ancestorsOf(selectedPath).forEach((p) => result.add(p));
    closed.forEach((p) => result.delete(p));
    opened.forEach((p) => result.add(p));
    return result;
  }, [nodes, selectedPath, opened, closed]);

  const toggle = (path: string) => {
    const expand = !open.has(path);
    setOpened((prev) => withItem(prev, path, expand));
    setClosed((prev) => withItem(prev, path, !expand));
  };

  return (
    <div className="ps-tree" data-testid="pack-tree">
      <div className="ps-pane-head">
        <span className="ps-pane-title">{t("tree.title")}</span>
        <button
          type="button"
          className="icon-btn"
          aria-label={t("tree.reload")}
          title={t("tree.reload")}
          onClick={() => void tree.refetch()}
          disabled={tree.isFetching}
        >
          {tree.isFetching ? (
            <Spinner size="sm" />
          ) : (
            <RefreshCw size="0.75rem" />
          )}
        </button>
      </div>
      {tree.isPending ? (
        <div className="flex justify-center" style={{ padding: "1rem" }}>
          <Spinner size="sm" />
        </div>
      ) : tree.isError ? (
        <ErrorState
          compact
          description={packErrorText(tree.error)}
          onRetry={() => void tree.refetch()}
        />
      ) : (
        <>
          {tree.data.truncated && (
            <Notice tone="warn" role="status" text={t("tree.truncated")} />
          )}
          {nodes.length === 0 ? (
            <p className="ps-pane-empty">{t("tree.empty")}</p>
          ) : (
            <ul
              role="tree"
              aria-label={t("tree.title")}
              className="ps-tree-root"
            >
              {nodes.map((node) => (
                <TreeNode
                  key={node.path}
                  node={node}
                  depth={0}
                  open={open}
                  toggle={toggle}
                  selectedPath={selectedPath}
                  onSelect={onSelect}
                  notes={notes}
                />
              ))}
            </ul>
          )}
        </>
      )}
    </div>
  );
};
