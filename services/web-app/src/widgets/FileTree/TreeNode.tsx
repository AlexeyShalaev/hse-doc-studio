import {
  ChevronDown,
  ChevronRight,
  FileCode,
  FileJson,
  FilePlus,
  FileText,
  FileType,
  Folder,
  FolderOpen,
  FolderPlus,
  Image,
  Lock,
} from "lucide-react";
import { clsx } from "clsx";
import {
  useEffect,
  useRef,
  useState,
  type CSSProperties,
  type MouseEvent as ReactMouseEvent,
} from "react";
import { useTranslation } from "react-i18next";
import type { FileNode } from "./lib/buildFileTree";

const DRAG_MIME = "application/x-hse-path";

/** Folder containing `path` ("" = project root). */
const parentOf = (path: string): string =>
  path.includes("/") ? path.slice(0, path.lastIndexOf("/")) : "";

/** Highlight applied to the row a dragged item would drop into. */
const DROP_TARGET_STYLE: CSSProperties = {
  background: "var(--accent-soft)",
  boxShadow: "inset 0 0 0 1px var(--accent-line)",
  borderRadius: "var(--r-2, 4px)",
};

type FileLeafIconProps = { path: string; active: boolean };

// Module-scope component so the per-file icon isn't "created during render".
const FileLeafIcon = ({ path, active }: FileLeafIconProps) => {
  const style: CSSProperties = {
    color: active ? "var(--accent)" : "var(--fg-3)",
    flexShrink: 0,
  };
  const lower = path.toLowerCase();
  if (/\.(tex|cls|sty|ltx|dtx|def)$/.test(lower))
    return <FileCode size={13} style={style} />;
  if (lower.endsWith(".json")) return <FileJson size={13} style={style} />;
  if (/\.(bib|bst)$/.test(lower)) return <FileType size={13} style={style} />;
  if (/\.(png|jpe?g|gif|svg|webp|pdf)$/.test(lower))
    return <Image size={13} style={style} />;
  return <FileText size={13} style={style} />;
};

/**
 * Inline name editor for rename/create — focuses + selects (name without
 * extension) on mount, commits on Enter/blur, cancels on Escape. A guard
 * prevents the blur-after-Enter double fire.
 */
export const InlineInput = ({
  initial,
  indent,
  placeholder,
  onSubmit,
  onCancel,
}: {
  initial: string;
  indent: number;
  placeholder?: string;
  onSubmit: (value: string) => void;
  onCancel: () => void;
}) => {
  const ref = useRef<HTMLInputElement>(null);
  const doneRef = useRef(false);

  useEffect(() => {
    const el = ref.current;
    if (!el) return;
    el.focus();
    const dot = initial.lastIndexOf(".");
    if (dot > 0) el.setSelectionRange(0, dot);
    else el.select();
  }, [initial]);

  const finish = (commit: boolean): void => {
    if (doneRef.current) return;
    doneRef.current = true;
    const value = ref.current?.value.trim() ?? "";
    if (commit && value) onSubmit(value);
    else onCancel();
  };

  return (
    <input
      ref={ref}
      defaultValue={initial}
      placeholder={placeholder}
      spellCheck={false}
      className="mono"
      style={{
        marginLeft: indent,
        marginRight: 6,
        flex: 1,
        minWidth: 0,
        fontSize: 12.5,
        padding: "1px 5px",
        background: "var(--bg-0)",
        border: "1px solid var(--accent)",
        borderRadius: "var(--r-2, 4px)",
        color: "var(--fg-0)",
        outline: "none",
      }}
      onKeyDown={(e) => {
        if (e.key === "Enter") {
          e.preventDefault();
          finish(true);
        } else if (e.key === "Escape") {
          e.preventDefault();
          finish(false);
        }
      }}
      onBlur={() => {
        finish(true);
      }}
      onClick={(e) => {
        e.stopPropagation();
      }}
    />
  );
};

export type TreeNodeContext = {
  selectedPath: string | undefined;
  isOpen: (path: string) => boolean;
  onToggle: (path: string) => void;
  onSelect: (node: FileNode) => void;
  onContextMenu: (node: FileNode, x: number, y: number) => void;
  /** Path of the node currently rendered as a rename input (or null). */
  editingPath: string | null;
  onRenameSubmit: (node: FileNode, newName: string) => void;
  onEditCancel: () => void;
  /** Folder under which a "new file"/"new folder" input is shown ("" = root). */
  creating: { parentPath: string; kind: "file" | "folder" } | null;
  onCreateSubmit: (
    parentPath: string,
    kind: "file" | "folder",
    name: string,
  ) => void;
  /** Move `src` (file/folder path) into `destFolder` ("" = root). */
  onMove: (src: string, destFolder: string) => void;
};

export type TreeNodeProps = {
  node: FileNode;
  depth: number;
  ctx: TreeNodeContext;
};

export const TreeNode = ({ node, depth, ctx }: TreeNodeProps) => {
  const { t } = useTranslation("appChrome");
  const indent = 8 + depth * 13;
  const [dragOver, setDragOver] = useState(false);
  const handleContextMenu = (e: ReactMouseEvent): void => {
    e.preventDefault();
    e.stopPropagation();
    ctx.onContextMenu(node, e.clientX, e.clientY);
  };

  const editing = ctx.editingPath === node.path;

  if (node.type === "folder") {
    const open = ctx.isOpen(node.path);
    const FolderIcon = open ? FolderOpen : Folder;
    const create = ctx.creating?.parentPath === node.path ? ctx.creating : null;
    return (
      <>
        {editing ? (
          <div className="flex items-center" style={{ paddingLeft: indent }}>
            <InlineInput
              initial={node.name}
              indent={0}
              onSubmit={(name) => {
                ctx.onRenameSubmit(node, name);
              }}
              onCancel={ctx.onEditCancel}
            />
          </div>
        ) : (
          <button
            type="button"
            className="row-btn"
            draggable={node.deletable}
            style={{
              paddingLeft: indent,
              gap: 5,
              opacity: node.isHidden ? 0.5 : 1,
              ...(dragOver ? DROP_TARGET_STYLE : null),
            }}
            onClick={() => {
              ctx.onToggle(node.path);
            }}
            onContextMenu={handleContextMenu}
            onDragStart={(e) => {
              e.dataTransfer.setData(DRAG_MIME, node.path);
              e.dataTransfer.effectAllowed = "move";
            }}
            onDragOver={(e) => {
              e.preventDefault();
              e.dataTransfer.dropEffect = "move";
              setDragOver(true);
            }}
            onDragLeave={() => {
              setDragOver(false);
            }}
            onDrop={(e) => {
              e.preventDefault();
              e.stopPropagation();
              setDragOver(false);
              const src = e.dataTransfer.getData(DRAG_MIME);
              if (src) ctx.onMove(src, node.path);
            }}
          >
            {open ? (
              <ChevronDown
                size={12}
                style={{ color: "var(--fg-3)", flexShrink: 0 }}
              />
            ) : (
              <ChevronRight
                size={12}
                style={{ color: "var(--fg-3)", flexShrink: 0 }}
              />
            )}
            <FolderIcon
              size={13}
              style={{ color: "var(--fg-2)", flexShrink: 0 }}
            />
            <span className="truncate">{node.name}</span>
          </button>
        )}
        {open && create && (
          <div
            className="flex items-center"
            style={{ paddingLeft: 8 + (depth + 1) * 13 + 17, gap: 4 }}
          >
            {create.kind === "folder" ? (
              <FolderPlus
                size={13}
                style={{ color: "var(--fg-3)", flexShrink: 0 }}
              />
            ) : (
              <FilePlus
                size={13}
                style={{ color: "var(--fg-3)", flexShrink: 0 }}
              />
            )}
            <InlineInput
              initial=""
              indent={0}
              placeholder={
                create.kind === "folder"
                  ? t("fileTree.folderNamePlaceholder")
                  : t("fileTree.fileNamePlaceholder")
              }
              onSubmit={(name) => {
                ctx.onCreateSubmit(node.path, create.kind, name);
              }}
              onCancel={ctx.onEditCancel}
            />
          </div>
        )}
        {open &&
          node.children?.map((child) => (
            <TreeNode
              key={child.path}
              node={child}
              depth={depth + 1}
              ctx={ctx}
            />
          ))}
      </>
    );
  }

  const isActive = ctx.selectedPath === node.path;
  if (editing) {
    return (
      <div className="flex items-center" style={{ paddingLeft: indent + 17 }}>
        <InlineInput
          initial={node.name}
          indent={0}
          onSubmit={(name) => {
            ctx.onRenameSubmit(node, name);
          }}
          onCancel={ctx.onEditCancel}
        />
      </div>
    );
  }
  return (
    <button
      type="button"
      className={clsx("row-btn", isActive && "active")}
      draggable={node.deletable}
      style={{
        paddingLeft: indent + 17,
        gap: 6,
        opacity: node.isHidden ? 0.5 : 1,
        ...(dragOver ? DROP_TARGET_STYLE : null),
      }}
      onClick={() => {
        ctx.onSelect(node);
      }}
      onContextMenu={handleContextMenu}
      onDragStart={(e) => {
        e.dataTransfer.setData(DRAG_MIME, node.path);
        e.dataTransfer.effectAllowed = "move";
      }}
      onDragOver={(e) => {
        e.preventDefault();
        e.dataTransfer.dropEffect = "move";
        setDragOver(true);
      }}
      onDragLeave={() => {
        setDragOver(false);
      }}
      onDrop={(e) => {
        // Dropping onto a file moves the dragged item into that file's folder,
        // not the project root. stopPropagation keeps the root-drop handler
        // (on the scroll container) from also firing.
        e.preventDefault();
        e.stopPropagation();
        setDragOver(false);
        const src = e.dataTransfer.getData(DRAG_MIME);
        if (src) ctx.onMove(src, parentOf(node.path));
      }}
      title={node.path}
    >
      <FileLeafIcon path={node.path} active={isActive} />
      <span className="truncate flex-1">{node.name}</span>
      {node.isReadOnly && (
        <Lock size={10} style={{ color: "var(--fg-3)", flexShrink: 0 }} />
      )}
    </button>
  );
};
