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
          style={{ width: "40rem", maxWidth: "calc(100vw - 2rem)" }}
        >
          {/* Header */}
          <div
            className="flex items-center gap-2"
            style={{
              padding: "0.875rem 1rem",
              borderBottom: "1px solid var(--border)",
              minWidth: 0,
            }}
          >
            <FolderOpen size="0.875rem" style={{ color: "var(--accent)" }} />
            <DialogPrimitive.Title
              style={{
                margin: 0,
                fontSize: "0.8125rem",
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
              <X size="0.875rem" />
            </DialogPrimitive.Close>
          </div>

          {/* Breadcrumbs */}
          <div
            className="flex items-center gap-1 overflow-x-auto"
            style={{
              padding: "0.5rem 0.875rem",
              borderBottom: "1px solid var(--border)",
              background: "var(--bg-0)",
              minHeight: "2.25rem",
              scrollbarWidth: "thin",
            }}
          >
            {crumbs.length === 0 ? (
              <span className="mono dim" style={{ fontSize: "0.6875rem" }}>
                {t("breadcrumbs.loading")}
              </span>
            ) : (
              crumbs.map((c, i) => (
                <span
                  key={c.path}
                  className="flex items-center"
                  style={{ gap: "0.125rem", minWidth: 0 }}
                >
                  {i > 0 && (
                    <ChevronRight
                      size="0.6875rem"
                      style={{
                        color: "var(--fg-3)",
                        flexShrink: 0,
                        margin: "0 0.125rem",
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
                      padding: "0.1875rem 0.375rem",
                      borderRadius: "var(--r-1)",
                      fontSize: "0.6875rem",
                      color:
                        i === crumbs.length - 1 ? "var(--fg-0)" : "var(--fg-2)",
                      fontWeight: i === crumbs.length - 1 ? 600 : 400,
                      cursor: i === crumbs.length - 1 ? "default" : "pointer",
                      whiteSpace: "nowrap",
                      display: "inline-flex",
                      alignItems: "center",
                      gap: "0.25rem",
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
                    {c.isRoot && <Home size="0.625rem" />}
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
                padding: "0.5rem 0.875rem",
                borderBottom: "1px solid var(--border)",
                background: "var(--bg-1)",
              }}
            >
              <div
                className="flex items-center"
                style={{
                  gap: "0.375rem",
                  padding: "0.25rem 0.5rem",
                  background: "var(--bg-2)",
                  border: "1px solid var(--border)",
                  borderRadius: "var(--r-2)",
                }}
              >
                <Search
                  size="0.75rem"
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
                    fontSize: "0.75rem",
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
                    <X size="0.6875rem" />
                  </button>
                )}
              </div>
            </div>
          )}

          {/* List */}
          <div
            style={{
              maxHeight: "50vh",
              minHeight: "15rem",
              overflowY: "auto",
              background: "var(--bg-1)",
            }}
          >
            {isLoading ? (
              <div
                className="flex items-center justify-center"
                style={{ padding: "2.5rem 1rem" }}
              >
                <Spinner />
              </div>
            ) : errorMessage ? (
              <div
                className="flex items-center gap-2"
                style={{
                  padding: "1rem",
                  color: "var(--c-err)",
                  fontSize: "0.75rem",
                }}
              >
                <AlertCircle size="0.875rem" style={{ flexShrink: 0 }} />
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
                  <div style={{ padding: "0.25rem 0.375rem" }}>
                    {data.parent && (
                      <button
                        type="button"
                        className="row-btn"
                        onClick={() => {
                          if (data.parent) navigate(data.parent);
                        }}
                      >
                        <CornerLeftUp
                          size="0.875rem"
                          style={{ color: "var(--fg-3)", flexShrink: 0 }}
                        />
                        <span className="mono dim">{t("list.up")}</span>
                      </button>
                    )}
                    {data.entries.length === 0 ? (
                      <div
                        className="dim"
                        style={{
                          padding: "1.5rem 0.75rem",
                          textAlign: "center",
                          fontSize: "0.75rem",
                        }}
                      >
                        {t("list.empty")}
                      </div>
                    ) : filtered.length === 0 ? (
                      <div
                        className="dim"
                        style={{
                          padding: "1.5rem 0.75rem",
                          textAlign: "center",
                          fontSize: "0.75rem",
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
                              size="0.875rem"
                              style={{
                                color: "var(--accent)",
                                flexShrink: 0,
                              }}
                            />
                          ) : (
                            <File
                              size="0.875rem"
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
                              style={{ fontSize: "0.625rem", flexShrink: 0 }}
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
                          padding: "0.375rem 0.75rem 0.125rem",
                          fontSize: "0.625rem",
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
                padding: "0.5rem 1rem",
                textAlign: "left",
                fontSize: "0.6875rem",
                cursor: "pointer",
                display: "flex",
                alignItems: "center",
                gap: "0.375rem",
              }}
            >
              <ChevronRight
                size="0.6875rem"
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
                style={{ padding: "0 1rem 0.75rem" }}
              >
                <div className="flex gap-2">
                  <input
                    type="text"
                    className="input mono"
                    style={{ fontSize: "0.71875rem", flex: 1 }}
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
              padding: "0.625rem 1rem",
              borderTop: "1px solid var(--border)",
              background: canConfirm ? "var(--accent-soft)" : "var(--bg-0)",
              minWidth: 0,
            }}
          >
            <div
              className="label-up"
              style={{
                color: canConfirm ? "var(--accent)" : "var(--fg-3)",
                marginBottom: "0.25rem",
              }}
            >
              {canConfirm ? t("preview.willSelect") : t("preview.navigateHint")}
            </div>
            <div className="flex items-center gap-2" style={{ minWidth: 0 }}>
              <Folder
                size="0.8125rem"
                style={{
                  color: canConfirm ? "var(--accent)" : "var(--fg-3)",
                  flexShrink: 0,
                }}
              />
              <span
                style={{
                  fontSize: "0.78125rem",
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
                  fontSize: "0.65625rem",
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
              padding: "0.75rem 1rem",
              borderTop: "1px solid var(--border)",
              background: "var(--bg-0)",
              gap: "0.5rem",
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
