import { useState } from "react";
import { useTranslation } from "react-i18next";
import * as DialogPrimitive from "@radix-ui/react-dialog";
import {
  AlertCircle,
  ChevronRight,
  CornerLeftUp,
  File,
  Folder,
  FolderOpen,
  Home,
  Search,
  X,
} from "lucide-react";
import { Spinner } from "@shared/ui/Spinner";
import { ApiError } from "@shared/api/client";
import { useBrowseFolder } from "../api/folderQueries";

export type FolderPickerModalProps = {
  isOpen: boolean;
  onClose: () => void;
  onSelect: (path: string) => void;
  initialPath?: string | null;
};

type Crumb = { label: string; path: string; isRoot?: boolean };

const splitIntoCrumbs = (absPath: string): Crumb[] => {
  const isWindows = /^[A-Za-z]:[\\/]/.test(absPath);
  if (isWindows) {
    const normalized = absPath.replace(/\//g, "\\");
    const drive = normalized.slice(0, 3); // "C:\"
    const tail = normalized.slice(3).replace(/\\+$/, "");
    if (tail === "") return [{ label: drive, path: drive, isRoot: true }];
    const parts = tail.split("\\").filter((p) => p !== "");
    const crumbs: Crumb[] = [{ label: drive, path: drive, isRoot: true }];
    let cur = drive;
    for (const p of parts) {
      cur = cur.endsWith("\\") ? cur + p : cur + "\\" + p;
      crumbs.push({ label: p, path: cur });
    }
    return crumbs;
  }
  const trimmed = absPath.replace(/\/+$/, "");
  const parts = trimmed.split("/").filter((p) => p !== "");
  const crumbs: Crumb[] = [{ label: "/", path: "/", isRoot: true }];
  let cur = "";
  for (const p of parts) {
    cur += "/" + p;
    crumbs.push({ label: p, path: cur });
  }
  return crumbs;
};

const hasInitial = (p?: string | null): boolean =>
  typeof p === "string" && p.trim().length > 0;

const folderName = (path: string): string => {
  const parts = path.split(/[/\\]/).filter((p) => p !== "");
  return parts.at(-1) ?? path;
};

export const FolderPickerModal = ({
  isOpen,
  onClose,
  onSelect,
  initialPath,
}: FolderPickerModalProps) => {
  const { t } = useTranslation("folderPicker");
  const [currentPath, setCurrentPath] = useState<string | null>(
    initialPath ?? null,
  );
  const [manualPath, setManualPath] = useState<string>(initialPath ?? "");
  const [manualExpanded, setManualExpanded] = useState(false);
  const [filter, setFilter] = useState("");
  // Prevents accidental "Выбрать эту папку" right after open when the modal
  // shows the default (home) directory. If the user opens the modal with an
  // initialPath, they already made a deliberate choice — confirm-ready.
  // Otherwise they must navigate at least once.
  const [hasDeliberateChoice, setHasDeliberateChoice] = useState(
    hasInitial(initialPath),
  );

  const [prevIsOpen, setPrevIsOpen] = useState(isOpen);
  if (isOpen !== prevIsOpen) {
    setPrevIsOpen(isOpen);
    if (isOpen) {
      setCurrentPath(initialPath ?? null);
      setManualPath(initialPath ?? "");
      setManualExpanded(false);
      setHasDeliberateChoice(hasInitial(initialPath));
      setFilter("");
    }
  }

  const { data, isLoading, error } = useBrowseFolder(currentPath, isOpen);

  const navigate = (path: string) => {
    setCurrentPath(path);
    setManualPath(path);
    setHasDeliberateChoice(true);
    setFilter("");
  };

  const handleManualSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    const trimmed = manualPath.trim();
    if (trimmed !== "") {
      setCurrentPath(trimmed);
      setHasDeliberateChoice(true);
      setFilter("");
    }
  };

  // Страж «сначала перейдите куда-нибудь» защищал от случайного подтверждения
  // домашнего каталога, куда браузер открывался по умолчанию. Когда приложение
  // работает в контейнере, по умолчанию открывается КОРЕНЬ смонтированной папки
  // пользователя — а это как раз тот каталог, который чаще всего и нужен, и
  // требовать от него лишнего шага незачем.
  const canConfirm = hasDeliberateChoice || (data?.is_root ?? false);

  const handleConfirm = () => {
    if (data?.path && canConfirm) {
      onSelect(data.path);
      onClose();
    }
  };

  const errorMessage =
    error instanceof ApiError
      ? error.detail
      : error instanceof Error
        ? error.message
        : null;

  const crumbs = data?.path ? splitIntoCrumbs(data.path) : [];

  return (
    <DialogPrimitive.Root
      open={isOpen}
      onOpenChange={(open) => {
        if (!open) onClose();
      }}
    >
      <DialogPrimitive.Portal>
        <DialogPrimitive.Overlay className="scrim" />
        <DialogPrimitive.Content
          className="modal-panel fixed left-1/2 top-1/2 z-[101] -translate-x-1/2 -translate-y-1/2"
          style={{ width: 640, maxWidth: "calc(100vw - 32px)" }}
        >
          {/* Header */}
          <div
            className="flex items-center gap-2"
            style={{
              padding: "14px 16px",
              borderBottom: "1px solid var(--border)",
              minWidth: 0,
            }}
          >
            <FolderOpen size={14} style={{ color: "var(--accent)" }} />
            <DialogPrimitive.Title
              style={{
                margin: 0,
                fontSize: 13,
                fontWeight: 600,
                letterSpacing: "-0.01em",
              }}
            >
              {t("modal.title")}
            </DialogPrimitive.Title>
            <span className="flex-1" />
            <DialogPrimitive.Close
              className="icon-btn"
              aria-label={t("modal.close")}
            >
              <X size={14} />
            </DialogPrimitive.Close>
          </div>

          {/* Breadcrumbs */}
          <div
            className="flex items-center gap-1 overflow-x-auto"
            style={{
              padding: "8px 14px",
              borderBottom: "1px solid var(--border)",
              background: "var(--bg-0)",
              minHeight: 36,
              scrollbarWidth: "thin",
            }}
          >
            {crumbs.length === 0 ? (
              <span className="mono dim" style={{ fontSize: 11 }}>
                {t("breadcrumbs.loading")}
              </span>
            ) : (
              crumbs.map((c, i) => (
                <span
                  key={c.path}
                  className="flex items-center"
                  style={{ gap: 2, minWidth: 0 }}
                >
                  {i > 0 && (
                    <ChevronRight
                      size={11}
                      style={{
                        color: "var(--fg-3)",
                        flexShrink: 0,
                        margin: "0 2px",
                      }}
                    />
                  )}
                  <button
                    type="button"
                    onClick={() => {
                      navigate(c.path);
                    }}
                    disabled={i === crumbs.length - 1}
                    className="mono"
                    style={{
                      background: "transparent",
                      border: 0,
                      padding: "3px 6px",
                      borderRadius: "var(--r-1)",
                      fontSize: 11,
                      color:
                        i === crumbs.length - 1 ? "var(--fg-0)" : "var(--fg-2)",
                      fontWeight: i === crumbs.length - 1 ? 600 : 400,
                      cursor: i === crumbs.length - 1 ? "default" : "pointer",
                      whiteSpace: "nowrap",
                      display: "inline-flex",
                      alignItems: "center",
                      gap: 4,
                      transition: "background 0.1s, color 0.1s",
                    }}
                    onMouseEnter={(e) => {
                      if (i !== crumbs.length - 1) {
                        e.currentTarget.style.background = "var(--bg-hover)";
                        e.currentTarget.style.color = "var(--fg-0)";
                      }
                    }}
                    onMouseLeave={(e) => {
                      if (i !== crumbs.length - 1) {
                        e.currentTarget.style.background = "transparent";
                        e.currentTarget.style.color = "var(--fg-2)";
                      }
                    }}
                  >
                    {c.isRoot && <Home size={10} />}
                    {c.label}
                  </button>
                </span>
              ))
            )}
          </div>

          {/* Filter */}
          {data && data.entries.length > 0 && (
            <div
              style={{
                padding: "8px 14px",
                borderBottom: "1px solid var(--border)",
                background: "var(--bg-1)",
              }}
            >
              <div
                className="flex items-center"
                style={{
                  gap: 6,
                  padding: "4px 8px",
                  background: "var(--bg-2)",
                  border: "1px solid var(--border)",
                  borderRadius: "var(--r-2)",
                }}
              >
                <Search
                  size={12}
                  style={{ color: "var(--fg-3)", flexShrink: 0 }}
                />
                <input
                  type="text"
                  value={filter}
                  onChange={(e) => {
                    setFilter(e.target.value);
                  }}
                  onKeyDown={(e) => {
                    if (e.key === "Escape" && filter !== "") {
                      e.stopPropagation();
                      setFilter("");
                    }
                  }}
                  placeholder={t("filter.placeholder")}
                  spellCheck={false}
                  style={{
                    flex: 1,
                    minWidth: 0,
                    background: "transparent",
                    border: 0,
                    outline: "none",
                    color: "var(--fg-0)",
                    fontSize: 12,
                    padding: 0,
                  }}
                />
                {filter !== "" && (
                  <button
                    type="button"
                    onClick={() => {
                      setFilter("");
                    }}
                    aria-label={t("filter.clear")}
                    style={{
                      background: "transparent",
                      border: 0,
                      color: "var(--fg-3)",
                      padding: 0,
                      cursor: "pointer",
                      display: "inline-flex",
                      alignItems: "center",
                    }}
                  >
                    <X size={11} />
                  </button>
                )}
              </div>
            </div>
          )}

          {/* List */}
          <div
            style={{
              maxHeight: "50vh",
              minHeight: 240,
              overflowY: "auto",
              background: "var(--bg-1)",
            }}
          >
            {isLoading ? (
              <div
                className="flex items-center justify-center"
                style={{ padding: "40px 16px" }}
              >
                <Spinner />
              </div>
            ) : errorMessage ? (
              <div
                className="flex items-center gap-2"
                style={{
                  padding: "16px",
                  color: "var(--c-err)",
                  fontSize: 12,
                }}
              >
                <AlertCircle size={14} style={{ flexShrink: 0 }} />
                <span>{errorMessage}</span>
              </div>
            ) : data ? (
              (() => {
                const q = filter.trim().toLowerCase();
                const filtered =
                  q === ""
                    ? data.entries
                    : data.entries.filter((e) =>
                        e.name.toLowerCase().includes(q),
                      );
                return (
                  <div style={{ padding: "4px 6px" }}>
                    {data.parent && (
                      <button
                        type="button"
                        className="row-btn"
                        onClick={() => {
                          if (data.parent) navigate(data.parent);
                        }}
                      >
                        <CornerLeftUp
                          size={14}
                          style={{ color: "var(--fg-3)", flexShrink: 0 }}
                        />
                        <span className="mono dim">{t("list.up")}</span>
                      </button>
                    )}
                    {data.entries.length === 0 ? (
                      <div
                        className="dim"
                        style={{
                          padding: "24px 12px",
                          textAlign: "center",
                          fontSize: 12,
                        }}
                      >
                        {t("list.empty")}
                      </div>
                    ) : filtered.length === 0 ? (
                      <div
                        className="dim"
                        style={{
                          padding: "24px 12px",
                          textAlign: "center",
                          fontSize: 12,
                        }}
                      >
                        {t("list.noResults")}{" "}
                        <span className="mono">«{filter}»</span>
                      </div>
                    ) : (
                      filtered.map((entry) => (
                        <button
                          key={entry.path}
                          type="button"
                          className="row-btn"
                          disabled={!entry.is_dir}
                          onClick={() => {
                            if (entry.is_dir) navigate(entry.path);
                          }}
                          style={{
                            opacity: entry.is_dir
                              ? entry.is_hidden
                                ? 0.6
                                : 1
                              : 0.45,
                            cursor: entry.is_dir ? "pointer" : "default",
                          }}
                        >
                          {entry.is_dir ? (
                            <Folder
                              size={14}
                              style={{
                                color: "var(--accent)",
                                flexShrink: 0,
                              }}
                            />
                          ) : (
                            <File
                              size={14}
                              style={{
                                color: "var(--fg-3)",
                                flexShrink: 0,
                              }}
                            />
                          )}
                          <span
                            style={{
                              overflow: "hidden",
                              textOverflow: "ellipsis",
                              whiteSpace: "nowrap",
                              minWidth: 0,
                              flex: 1,
                            }}
                          >
                            {entry.name}
                          </span>
                          {!entry.is_dir && (
                            <span
                              className="mono dimmer"
                              style={{ fontSize: 10, flexShrink: 0 }}
                            >
                              {t("list.file")}
                            </span>
                          )}
                        </button>
                      ))
                    )}
                    {q !== "" && filtered.length > 0 && (
                      <div
                        className="mono dim"
                        style={{
                          padding: "6px 12px 2px",
                          fontSize: 10,
                          textAlign: "right",
                        }}
                      >
                        {t("filter.count", {
                          shown: filtered.length,
                          total: data.entries.length,
                        })}
                      </div>
                    )}
                  </div>
                );
              })()
            ) : null}
          </div>

          {/* Manual path (collapsible) */}
          <div
            style={{
              borderTop: "1px solid var(--border)",
              background: "var(--bg-0)",
            }}
          >
            <button
              type="button"
              onClick={() => {
                setManualExpanded((v) => !v);
              }}
              className="mono dim"
              style={{
                width: "100%",
                background: "transparent",
                border: 0,
                padding: "8px 16px",
                textAlign: "left",
                fontSize: 11,
                cursor: "pointer",
                display: "flex",
                alignItems: "center",
                gap: 6,
              }}
            >
              <ChevronRight
                size={11}
                style={{
                  transform: manualExpanded ? "rotate(90deg)" : "none",
                  transition: "transform 0.15s",
                }}
              />
              {t("manual.toggle")}
            </button>
            {manualExpanded && (
              <form
                onSubmit={handleManualSubmit}
                style={{ padding: "0 16px 12px" }}
              >
                <div className="flex gap-2">
                  <input
                    type="text"
                    className="input mono"
                    style={{ fontSize: 11.5, flex: 1 }}
                    value={manualPath}
                    onChange={(e) => {
                      setManualPath(e.target.value);
                    }}
                    placeholder={t("manual.placeholder")}
                    spellCheck={false}
                    autoFocus
                  />
                  <button type="submit" className="btn sm">
                    {t("manual.go")}
                  </button>
                </div>
              </form>
            )}
          </div>

          {/* Selection preview */}
          <div
            style={{
              padding: "10px 16px",
              borderTop: "1px solid var(--border)",
              background: canConfirm ? "var(--accent-soft)" : "var(--bg-0)",
              minWidth: 0,
            }}
          >
            <div
              className="label-up"
              style={{
                color: canConfirm ? "var(--accent)" : "var(--fg-3)",
                marginBottom: 4,
              }}
            >
              {canConfirm ? t("preview.willSelect") : t("preview.navigateHint")}
            </div>
            <div className="flex items-center gap-2" style={{ minWidth: 0 }}>
              <Folder
                size={13}
                style={{
                  color: canConfirm ? "var(--accent)" : "var(--fg-3)",
                  flexShrink: 0,
                }}
              />
              <span
                style={{
                  fontSize: 12.5,
                  fontWeight: 600,
                  color: "var(--fg-0)",
                  flexShrink: 0,
                }}
              >
                {data?.path ? folderName(data.path) : "—"}
              </span>
              <span
                className="mono dim"
                style={{
                  fontSize: 10.5,
                  overflow: "hidden",
                  textOverflow: "ellipsis",
                  whiteSpace: "nowrap",
                  minWidth: 0,
                  flex: 1,
                }}
                title={data?.path ?? ""}
              >
                {data?.path ?? ""}
              </span>
            </div>
          </div>

          {/* Footer */}
          <div
            className="flex items-center justify-end"
            style={{
              padding: "12px 16px",
              borderTop: "1px solid var(--border)",
              background: "var(--bg-0)",
              gap: 8,
            }}
          >
            <button type="button" className="btn ghost sm" onClick={onClose}>
              {t("footer.cancel")}
            </button>
            <button
              type="button"
              className="btn primary sm"
              onClick={handleConfirm}
              disabled={!data?.path || isLoading || !canConfirm}
              title={!canConfirm ? t("footer.confirmDisabledHint") : ""}
            >
              {data?.path
                ? t("footer.confirmNamed", { name: folderName(data.path) })
                : t("footer.confirm")}
            </button>
          </div>
        </DialogPrimitive.Content>
      </DialogPrimitive.Portal>
    </DialogPrimitive.Root>
  );
};
