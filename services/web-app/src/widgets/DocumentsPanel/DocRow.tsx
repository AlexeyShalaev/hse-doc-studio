import { type FocusEvent, type ReactNode, useEffect, useState } from "react";
import { Download, MoreVertical, RefreshCw, Upload } from "lucide-react";
import { clsx } from "clsx";
import * as DropdownMenu from "@radix-ui/react-dropdown-menu";
import { useTranslation } from "react-i18next";
import { useCustomFileActions } from "@entities/document";
import type { DocStatus, getDocMeta } from "@entities/document";
import { shortReason, useCompileSlot } from "@entities/compile";
import { useRouteEditGuard } from "@entities/signing-route";
import { DocBuildSubline } from "@features/cloud-builds";
import { UploadCustomFileModal } from "@features/custom-document";
import { env } from "@shared/config";
import { Modal } from "@shared/ui";
import { Spinner } from "@shared/ui/Spinner";
import { toast } from "@shared/lib";
import { DocStateLine } from "./DocStateLine";
import type { DocumentItem } from "./lib/buildDocSections";

const STATUS_TO_DOT: Record<DocStatus, string> = {
  ok: "ok",
  warn: "warn",
  err: "err",
  draft: "info",
  locked: "info",
  building: "info",
};

const customFileDownloadUrl = (projectId: string, relPath: string): string =>
  `${env.VITE_API_BASE_URL}/api/v1/projects/${projectId}/files/${relPath}`;

// Подсветка совпадений фильтра. Регистронезависимое подстрочное совпадение —
// того же вида, что и предикат фильтрации в DocumentsPanel, иначе строка
// прошла бы фильтр без единого <mark>.
const renderHighlighted = (text: string, query: string): ReactNode => {
  const needle = query.trim().toLowerCase();
  if (needle === "") return text;
  const haystack = text.toLowerCase();
  let from = 0;
  let at = haystack.indexOf(needle, from);
  if (at === -1) return text;
  const parts: ReactNode[] = [];
  let markIndex = 0;
  while (at !== -1) {
    if (at > from) parts.push(text.slice(from, at));
    parts.push(
      <mark key={`m${String(markIndex)}`} className="nav-mark">
        {text.slice(at, at + needle.length)}
      </mark>,
    );
    markIndex += 1;
    from = at + needle.length;
    at = haystack.indexOf(needle, from);
  }
  if (from < text.length) parts.push(text.slice(from));
  return parts;
};

const useMinuteNow = (): number => {
  const [now, setNow] = useState(() => Date.now());
  useEffect(() => {
    const id = window.setInterval(() => {
      setNow(Date.now());
    }, 30_000);
    return () => {
      window.clearInterval(id);
    };
  }, []);
  return now;
};

export type DocRowProps = {
  projectId: string;
  doc: DocumentItem;
  meta: ReturnType<typeof getDocMeta>;
  isActive: boolean;
  isBuilding: boolean;
  /** Текущая строка фильтра — подсвечивается в коде и названии документа. */
  query: string;
  onSelectDoc: (docId: string) => void;
};

// Wraps the doc row button with a kebab menu (replace/revert/download the
// custom file) and a compact "Кастомный" chip when the doc's normal
// pack-generated artifact has been swapped for a user-uploaded one.
export const DocRow = ({
  projectId,
  doc,
  meta,
  isActive,
  isBuilding,
  query,
  onSelectDoc,
}: DocRowProps) => {
  const { t } = useTranslation("documents");
  const [uploadOpen, setUploadOpen] = useState(false);
  const [revertConfirmOpen, setRevertConfirmOpen] = useState(false);
  const [isHovered, setIsHovered] = useState(false);
  const [isFocusWithin, setIsFocusWithin] = useState(false);
  const [isMenuOpen, setIsMenuOpen] = useState(false);
  const now = useMinuteNow();
  const slot = useCompileSlot(projectId, doc.id);
  const hasLiveSlot = slot?.status === "running";
  const { remove, isRemoving } = useCustomFileActions(projectId, doc.id);
  const routeGuard = useRouteEditGuard(projectId);
  const isCustom = doc.custom_file != null;
  const sev = isBuilding ? "building" : STATUS_TO_DOT[doc.status];
  const errors = doc.errors ?? 0;
  const warnings = doc.warnings ?? 0;
  // Кебаб съедал ~22px ширины в каждой строке 260-пиксельной панели, поэтому
  // он схлопнут в ноль, пока строка не под курсором / не в фокусе. Скрываем
  // прозрачностью и нулевой шириной, а не visibility/display — иначе кнопка
  // выпала бы из порядка обхода Tab и стала недостижимой с клавиатуры.
  const isKebabVisible = isHovered || isFocusWithin || isMenuOpen;

  const handleRevert = () => {
    routeGuard.run({ docIds: [doc.id] }, () => {
      remove(false)
        .then(() => {
          toast.success(t("customFile.revertedToast"));
          setRevertConfirmOpen(false);
        })
        .catch(() => {
          // per-request error toast already shown by the axios interceptor
        });
    });
  };

  const handleBlur = (event: FocusEvent<HTMLDivElement>) => {
    // Переход фокуса между кнопкой строки и кебабом не считается уходом.
    if (event.currentTarget.contains(event.relatedTarget)) return;
    setIsFocusWithin(false);
  };

  return (
    <div
      className="flex items-center doc-row"
      style={{ gap: "0.125rem" }}
      onMouseEnter={() => {
        setIsHovered(true);
      }}
      onMouseLeave={() => {
        setIsHovered(false);
      }}
      onFocus={() => {
        setIsFocusWithin(true);
      }}
      onBlur={handleBlur}
    >
      <button
        type="button"
        className={clsx("row-btn doc-row-btn", isActive && "active")}
        onClick={() => {
          onSelectDoc(doc.id);
        }}
        style={{ alignItems: "center", gap: "0.5rem", flex: 1, minWidth: 0 }}
      >
        <span className={"dot " + sev} />
        <span
          className="mono doc-code"
          style={{
            fontSize: "0.65625rem",
            color: isActive ? "var(--accent)" : "var(--fg-3)",
            letterSpacing: "0.02em",
          }}
          title={meta.code}
        >
          {renderHighlighted(meta.code, query)}
        </span>
        <span
          className="doc-main"
          style={{
            fontSize: "0.75rem",
            lineHeight: 1.35,
            gap: 1,
            overflowWrap: "anywhere",
          }}
        >
          <span title={meta.name}>{renderHighlighted(meta.name, query)}</span>
          <DocStateLine
            projectId={projectId}
            docId={doc.id}
            status={doc.status}
          />
          {!hasLiveSlot && (
            <DocBuildSubline projectId={projectId} docId={doc.id} now={now} />
          )}
          {doc.status === "err" && doc.last_compile_error && (
            <span
              data-testid={`doc-failure-${doc.id}`}
              data-code={doc.last_compile_error.code}
              title={doc.last_compile_error.message}
              className="doc-failure"
              style={{
                fontSize: "0.65625rem",
                lineHeight: 1.3,
                color: "var(--c-err)",
              }}
            >
              {shortReason(doc.last_compile_error.message)}
            </span>
          )}
        </span>
        {isCustom && (
          <span
            className="chip doc-chip"
            style={{
              flexShrink: 0,
              fontSize: "0.5625rem",
              padding: "1px 0.375rem",
              background: "var(--bg-3)",
              color: "var(--fg-2)",
            }}
          >
            {t("customFile.badge")}
          </span>
        )}
        {(errors > 0 || warnings > 0) && (
          <span
            className="mono shrink-0 doc-counts"
            style={{
              fontSize: "0.59375rem",
              color: errors > 0 ? "var(--c-err)" : "var(--c-warn)",
              letterSpacing: "0.04em",
            }}
          >
            {errors > 0 ? `${String(errors)}E` : ""}
            {errors > 0 && warnings > 0 ? " " : ""}
            {warnings > 0 ? `${String(warnings)}W` : ""}
          </span>
        )}
      </button>
      <DropdownMenu.Root open={isMenuOpen} onOpenChange={setIsMenuOpen}>
        <DropdownMenu.Trigger asChild>
          <button
            type="button"
            className="icon-btn sm"
            style={{
              flexShrink: 0,
              opacity: isKebabVisible ? 1 : 0,
              width: isKebabVisible ? "1.375rem" : 0,
              overflow: "hidden",
              pointerEvents: isKebabVisible ? "auto" : "none",
              transition: "opacity 0.1s",
            }}
            aria-label={t("customFile.replaceMenuItem")}
          >
            <MoreVertical size="0.75rem" />
          </button>
        </DropdownMenu.Trigger>
        <DropdownMenu.Portal>
          <DropdownMenu.Content
            className={clsx(
              "z-50 min-w-[13rem] overflow-hidden rounded-r-3 border border-border bg-bg-1",
              "shadow-elev-pop",
              "data-[state=open]:animate-in data-[state=open]:fade-in-0 data-[state=open]:zoom-in-95",
              "data-[state=closed]:animate-out data-[state=closed]:fade-out-0 data-[state=closed]:zoom-out-95",
              "origin-top-right",
            )}
            sideOffset={4}
            align="start"
          >
            <DropdownMenu.Item
              className={clsx(
                "flex cursor-pointer select-none items-center gap-2 outline-none",
                "focus:bg-bg-hover",
              )}
              style={{ padding: "0.5rem 0.75rem", fontSize: "0.78125rem" }}
              onSelect={() => {
                setUploadOpen(true);
              }}
            >
              <Upload size="0.75rem" />
              <span>{t("customFile.replaceMenuItem")}</span>
            </DropdownMenu.Item>
            {isCustom && (
              <DropdownMenu.Item
                className={clsx(
                  "flex cursor-pointer select-none items-center gap-2 outline-none",
                  "focus:bg-bg-hover",
                )}
                style={{ padding: "0.5rem 0.75rem", fontSize: "0.78125rem" }}
                onSelect={() => {
                  setRevertConfirmOpen(true);
                }}
              >
                <RefreshCw size="0.75rem" />
                <span>{t("customFile.revertMenuItem")}</span>
              </DropdownMenu.Item>
            )}
            {isCustom && (
              <DropdownMenu.Item asChild>
                <a
                  href={customFileDownloadUrl(projectId, doc.output_file ?? "")}
                  download
                  className={clsx(
                    "flex cursor-pointer select-none items-center gap-2 outline-none",
                    "focus:bg-bg-hover",
                  )}
                  style={{ padding: "0.5rem 0.75rem", fontSize: "0.78125rem" }}
                >
                  <Download size="0.75rem" />
                  <span>{t("customFile.downloadMenuItem")}</span>
                </a>
              </DropdownMenu.Item>
            )}
          </DropdownMenu.Content>
        </DropdownMenu.Portal>
      </DropdownMenu.Root>

      <UploadCustomFileModal
        isOpen={uploadOpen}
        onClose={() => {
          setUploadOpen(false);
        }}
        projectId={projectId}
        docId={doc.id}
        docName={meta.name}
      />
      <Modal
        isOpen={revertConfirmOpen}
        onClose={() => {
          setRevertConfirmOpen(false);
        }}
        title={t("customFile.revertConfirmTitle")}
        description={t("customFile.revertConfirmDescription")}
        footer={
          <>
            <button
              type="button"
              className="btn"
              onClick={() => {
                setRevertConfirmOpen(false);
              }}
              disabled={isRemoving}
            >
              {t("customFile.cancel")}
            </button>
            <button
              type="button"
              className="btn primary"
              onClick={handleRevert}
              disabled={isRemoving}
            >
              {isRemoving && <Spinner size="sm" />}
              {t("customFile.revertConfirmAction")}
            </button>
          </>
        }
      />
    </div>
  );
};
