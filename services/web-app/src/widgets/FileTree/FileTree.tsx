import { useCallback, useEffect, useMemo, useState } from "react";
import { useTranslation } from "react-i18next";
import {
  AlertTriangle,
  FilePlus,
  FolderPlus,
  Lock,
  Pencil,
  Trash2,
} from "lucide-react";
import {
  useCreateDir,
  useDeleteFile,
  useFileTree,
  useMoveFile,
  useUploadFile,
} from "@entities/document";
import { Modal, Spinner } from "@shared/ui";
import {
  ancestorFolders,
  buildFileTree,
  type FileNode,
} from "./lib/buildFileTree";
import { InlineInput, TreeNode, type TreeNodeContext } from "./TreeNode";

export type FileTreeProps = {
  projectId: string;
  selectedPath: string | undefined;
  onSelect: (node: FileNode) => void;
  /**
   * Show build artifacts and dot-directories. The tree is the BODY of the
   * Files panel now: the shell owns the frame (border, background, header) and
   * therefore owns the "показать сгенерированные" toggle that used to live in
   * this component's own header. Omitted → hidden files stay hidden.
   */
  showHidden?: boolean;
};

// `node: null` is the root menu, opened by right-clicking empty space.
type ContextMenu = { node: FileNode | null; x: number; y: number };
type CreateState = { parentPath: string; kind: "file" | "folder" };

const DRAG_MIME = "application/x-hse-path";

const parentOf = (path: string): string =>
  path.includes("/") ? path.slice(0, path.lastIndexOf("/")) : "";

const basenameOf = (path: string): string =>
  path.includes("/") ? path.slice(path.lastIndexOf("/") + 1) : path;

type FileTreeMenuProps = {
  menu: ContextMenu;
  onCreate: (parentPath: string, kind: "file" | "folder") => void;
  onRename: (node: FileNode) => void;
  onDelete: (node: FileNode) => void;
  onClose: () => void;
};

/** The right-click popover — root variant (`menu.node === null`) or per-node. */
const FileTreeMenu = ({
  menu,
  onCreate,
  onRename,
  onDelete,
  onClose,
}: FileTreeMenuProps) => {
  const { t } = useTranslation("appChrome");
  const { node } = menu;
  return (
    <div
      className="flex flex-col"
      style={{
        position: "fixed",
        left: Math.min(menu.x, window.innerWidth - 210),
        top: Math.min(menu.y, window.innerHeight - 130),
        width: 200,
        zIndex: 61,
        background: "var(--bg-1)",
        border: "1px solid var(--border)",
        borderRadius: "var(--r-3)",
        boxShadow: "var(--shadow-pop, 0 12px 40px rgba(0,0,0,0.45))",
        padding: 4,
      }}
      onClick={(e) => {
        e.stopPropagation();
      }}
    >
      {node === null ? (
        <>
          <div className="dimmer" style={{ fontSize: 10, padding: "4px 8px" }}>
            {t("fileTree.projectRoot")}
          </div>
          <button
            type="button"
            className="row-btn"
            style={{ gap: 8 }}
            onClick={() => {
              onCreate("", "file");
              onClose();
            }}
          >
            <FilePlus size={13} style={{ flexShrink: 0 }} />
            <span>{t("fileTree.newFile")}</span>
          </button>
          <button
            type="button"
            className="row-btn"
            style={{ gap: 8 }}
            onClick={() => {
              onCreate("", "folder");
              onClose();
            }}
          >
            <FolderPlus size={13} style={{ flexShrink: 0 }} />
            <span>{t("fileTree.newFolder")}</span>
          </button>
        </>
      ) : (
        <>
          <div
            className="mono dimmer truncate"
            style={{ fontSize: 10, padding: "4px 8px" }}
          >
            {node.path}
          </div>
          {node.type === "folder" && (
            <>
              <button
                type="button"
                className="row-btn"
                style={{ gap: 8 }}
                onClick={() => {
                  onCreate(node.path, "file");
                  onClose();
                }}
              >
                <FilePlus size={13} style={{ flexShrink: 0 }} />
                <span>{t("fileTree.newFileHere")}</span>
              </button>
              <button
                type="button"
                className="row-btn"
                style={{ gap: 8 }}
                onClick={() => {
                  onCreate(node.path, "folder");
                  onClose();
                }}
              >
                <FolderPlus size={13} style={{ flexShrink: 0 }} />
                <span>{t("fileTree.newFolderHere")}</span>
              </button>
            </>
          )}
          {node.deletable ? (
            <>
              <button
                type="button"
                className="row-btn"
                style={{ gap: 8 }}
                onClick={() => {
                  onRename(node);
                  onClose();
                }}
              >
                <Pencil size={13} style={{ flexShrink: 0 }} />
                <span>{t("fileTree.rename")}</span>
              </button>
              <button
                type="button"
                className="row-btn"
                style={{ gap: 8, color: "var(--c-err)" }}
                onClick={() => {
                  onDelete(node);
                  onClose();
                }}
              >
                <Trash2 size={13} style={{ flexShrink: 0 }} />
                <span>{t("fileTree.delete")}</span>
              </button>
            </>
          ) : (
            <div
              className="dimmer"
              style={{
                gap: 8,
                padding: "6px 8px",
                fontSize: 11.5,
                display: "flex",
                alignItems: "center",
              }}
              title={t("fileTree.protectedTitle")}
            >
              <Lock size={13} style={{ flexShrink: 0 }} />
              <span>{t("fileTree.protected")}</span>
            </div>
          )}
        </>
      )}
    </div>
  );
};

export const FileTree = ({
  projectId,
  selectedPath,
  onSelect,
  showHidden = false,
}: FileTreeProps) => {
  const { t } = useTranslation("appChrome");
  const { data: items, isLoading, isError } = useFileTree(projectId);
  const [menu, setMenu] = useState<ContextMenu | null>(null);
  const [editingPath, setEditingPath] = useState<string | null>(null);
  const [creating, setCreating] = useState<CreateState | null>(null);
  const [deleteTarget, setDeleteTarget] = useState<FileNode | null>(null);
  const [overrides, setOverrides] = useState<Map<string, boolean>>(new Map());

  const deleteFile = useDeleteFile();
  const moveFile = useMoveFile();
  const uploadFile = useUploadFile();
  const createDir = useCreateDir();

  const tree = useMemo(
    () => buildFileTree(items ?? [], showHidden),
    [items, showHidden],
  );

  const defaultOpen = useMemo(() => {
    const open = new Set<string>();
    for (const node of tree) {
      if (node.type === "folder") open.add(node.path);
    }
    if (selectedPath) {
      for (const folder of ancestorFolders(selectedPath)) open.add(folder);
    }
    return open;
  }, [tree, selectedPath]);

  const isOpen = useCallback(
    (path: string): boolean => overrides.get(path) ?? defaultOpen.has(path),
    [overrides, defaultOpen],
  );

  const toggle = useCallback(
    (path: string): void => {
      setOverrides((prev) => {
        const open = prev.get(path) ?? defaultOpen.has(path);
        const next = new Map(prev);
        next.set(path, !open);
        return next;
      });
    },
    [defaultOpen],
  );

  const forceOpen = useCallback((path: string): void => {
    setOverrides((prev) => {
      const next = new Map(prev);
      next.set(path, true);
      return next;
    });
  }, []);

  const openContextMenu = useCallback(
    (node: FileNode, x: number, y: number): void => {
      setMenu({ node, x, y });
    },
    [],
  );

  const startCreate = useCallback(
    (parentPath: string, kind: "file" | "folder"): void => {
      setEditingPath(null);
      setCreating({ parentPath, kind });
      if (parentPath) forceOpen(parentPath);
    },
    [forceOpen],
  );

  const onCreateSubmit = useCallback(
    (parentPath: string, kind: "file" | "folder", name: string): void => {
      setCreating(null);
      const path = parentPath ? `${parentPath}/${name}` : name;
      if (kind === "folder") {
        createDir.mutate({ projectId, path });
      } else {
        uploadFile.mutate({
          projectId,
          path,
          data: new Blob([""]),
          contentType: "text/plain; charset=utf-8",
        });
      }
    },
    [projectId, uploadFile, createDir],
  );

  const onRenameSubmit = useCallback(
    (node: FileNode, newName: string): void => {
      setEditingPath(null);
      const parent = parentOf(node.path);
      const dst = parent ? `${parent}/${newName}` : newName;
      if (dst !== node.path)
        moveFile.mutate({ projectId, src: node.path, dst });
    },
    [projectId, moveFile],
  );

  const onMove = useCallback(
    (src: string, destFolder: string): void => {
      const srcParent = parentOf(src);
      // No-op if dropped in the same folder, onto itself, or into its own subtree.
      if (destFolder === srcParent) return;
      if (destFolder === src || destFolder.startsWith(`${src}/`)) return;
      const dst = destFolder
        ? `${destFolder}/${basenameOf(src)}`
        : basenameOf(src);
      moveFile.mutate({ projectId, src, dst });
    },
    [projectId, moveFile],
  );

  const onEditCancel = useCallback((): void => {
    setEditingPath(null);
    setCreating(null);
  }, []);

  const requestDelete = useCallback((node: FileNode): void => {
    if (!node.deletable) return;
    setDeleteTarget(node);
  }, []);

  const confirmDelete = useCallback((): void => {
    if (!deleteTarget) return;
    deleteFile.mutate(
      { projectId, path: deleteTarget.path },
      {
        onSettled: () => {
          setDeleteTarget(null);
        },
      },
    );
  }, [deleteTarget, projectId, deleteFile]);

  const ctx: TreeNodeContext = useMemo(
    () => ({
      selectedPath,
      isOpen,
      onToggle: toggle,
      onSelect,
      onContextMenu: openContextMenu,
      editingPath,
      onRenameSubmit,
      onEditCancel,
      creating,
      onCreateSubmit,
      onMove,
    }),
    [
      selectedPath,
      isOpen,
      toggle,
      onSelect,
      openContextMenu,
      editingPath,
      onRenameSubmit,
      onEditCancel,
      creating,
      onCreateSubmit,
      onMove,
    ],
  );

  useEffect(() => {
    if (!menu) return undefined;
    const close = (): void => {
      setMenu(null);
    };
    window.addEventListener("click", close);
    window.addEventListener("scroll", close, true);
    return () => {
      window.removeEventListener("click", close);
      window.removeEventListener("scroll", close, true);
    };
  }, [menu]);

  // No border, background, header or width of its own: the tree fills whatever
  // the shell gives it (the Files panel's `.panel-body`), which owns the frame.
  return (
    <div className="flex flex-col" style={{ height: "100%", minHeight: 0 }}>
      <div
        style={{
          flex: 1,
          minHeight: 0,
          overflowY: "auto",
          padding: "2px 0 10px",
        }}
        onContextMenu={(e) => {
          // Right-clicking empty space (not a row — rows stopPropagation) opens
          // the root menu to create a file/folder at the project root.
          e.preventDefault();
          setMenu({ node: null, x: e.clientX, y: e.clientY });
        }}
        onDragOver={(e) => {
          e.preventDefault();
        }}
        onDrop={(e) => {
          const src = e.dataTransfer.getData(DRAG_MIME);
          if (src) onMove(src, "");
        }}
      >
        {creating?.parentPath === "" && (
          <div
            className="flex items-center"
            style={{ paddingLeft: 8 + 17, gap: 4 }}
          >
            {creating.kind === "folder" ? (
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
                creating.kind === "folder"
                  ? t("fileTree.folderNamePlaceholder")
                  : t("fileTree.fileNamePlaceholder")
              }
              onSubmit={(name) => {
                onCreateSubmit("", creating.kind, name);
              }}
              onCancel={onEditCancel}
            />
          </div>
        )}
        {isLoading ? (
          <div className="flex justify-center" style={{ padding: 20 }}>
            <Spinner size="sm" />
          </div>
        ) : isError ? (
          <div className="dim" style={{ padding: 14, fontSize: 12 }}>
            {t("fileTree.loadError")}
          </div>
        ) : tree.length === 0 ? (
          <div className="dim" style={{ padding: 14, fontSize: 12 }}>
            {t("fileTree.emptyTree")}
          </div>
        ) : (
          tree.map((node) => (
            <TreeNode key={node.path} node={node} depth={0} ctx={ctx} />
          ))
        )}
      </div>

      {menu && (
        <FileTreeMenu
          menu={menu}
          onCreate={startCreate}
          onRename={(node) => {
            setEditingPath(node.path);
          }}
          onDelete={requestDelete}
          onClose={() => {
            setMenu(null);
          }}
        />
      )}

      <Modal
        isOpen={deleteTarget !== null}
        onClose={() => {
          if (!deleteFile.isPending) setDeleteTarget(null);
        }}
        title={
          deleteTarget?.type === "folder"
            ? t("fileTree.deleteFolderTitle")
            : t("fileTree.deleteFileTitle")
        }
        width={440}
        footer={
          <div className="flex items-center justify-end" style={{ gap: 8 }}>
            <button
              type="button"
              className="btn"
              onClick={() => {
                setDeleteTarget(null);
              }}
              disabled={deleteFile.isPending}
            >
              {t("fileTree.cancel")}
            </button>
            <button
              type="button"
              className="btn danger"
              onClick={confirmDelete}
              disabled={deleteFile.isPending}
            >
              {deleteFile.isPending ? (
                <Spinner size="sm" />
              ) : (
                <Trash2 size={13} />
              )}
              {t("fileTree.delete")}
            </button>
          </div>
        }
      >
        {deleteTarget && (
          <div className="flex items-start" style={{ gap: 10 }}>
            <div
              className="flex items-center justify-center"
              style={{
                width: 30,
                height: 30,
                flexShrink: 0,
                borderRadius: "var(--r-2)",
                background: "var(--c-err-soft)",
                color: "var(--c-err)",
              }}
            >
              <AlertTriangle size={15} />
            </div>
            <div className="flex flex-col" style={{ gap: 6, minWidth: 0 }}>
              <span
                style={{ fontSize: 13, lineHeight: 1.5, color: "var(--fg-1)" }}
              >
                {deleteTarget.type === "folder"
                  ? t("fileTree.deleteFolderConfirm")
                  : t("fileTree.deleteFileConfirm")}
              </span>
              <span
                className="mono dim"
                style={{ fontSize: 11.5, wordBreak: "break-all" }}
              >
                {deleteTarget.path}
              </span>
            </div>
          </div>
        )}
      </Modal>
    </div>
  );
};
