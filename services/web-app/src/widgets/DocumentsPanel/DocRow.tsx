import { type FocusEvent, type ReactNode, useState } from "react";
import { Download, MoreVertical, RefreshCw, Upload } from "lucide-react";
import { clsx } from "clsx";
import * as DropdownMenu from "@radix-ui/react-dropdown-menu";
import { useTranslation } from "react-i18next";
import { useCustomFileActions } from "@entities/document";
import type { DocStatus, getDocMeta } from "@entities/document";
import { UploadCustomFileModal } from "@features/custom-document";
import { env } from "@shared/config";
import { Modal } from "@shared/ui";
import { Spinner } from "@shared/ui/Spinner";
import { toast } from "@shared/lib";
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
  const { remove, isRemoving } = useCustomFileActions(projectId, doc.id);
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
    remove(false)
      .then(() => {
        toast.success(t("customFile.revertedToast"));
        setRevertConfirmOpen(false);
      })
      .catch(() => {
        // per-request error toast already shown by the axios interceptor
      });
  };

  const handleBlur = (event: FocusEvent<HTMLDivElement>) => {
    // Переход фокуса между кнопкой строки и кебабом не считается уходом.
    if (event.currentTarget.contains(event.relatedTarget)) return;
    setIsFocusWithin(false);
  };

  return (
    <div
      className="flex items-center"
      style={{ gap: 2 }}
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
        className={clsx("row-btn", isActive && "active")}
        onClick={() => {
          onSelectDoc(doc.id);
        }}
        style={{ alignItems: "center", gap: 8, flex: 1, minWidth: 0 }}
      >
        <span className={"dot " + sev} />
        <span
          className="mono shrink-0"
          style={{
            fontSize: 10.5,
            color: isActive ? "var(--accent)" : "var(--fg-3)",
            // minWidth keeps the code column aligned; a longer code
            // pushes the name instead of overlapping it.
            minWidth: 28,
            whiteSpace: "nowrap",
            letterSpacing: "0.02em",
          }}
        >
          {renderHighlighted(meta.code, query)}
        </span>
        <span
          className="flex-1 min-w-0"
          style={{ fontSize: 12, lineHeight: 1.35, minWidth: 0 }}
        >
          {renderHighlighted(meta.name, query)}
        </span>
        {isCustom && (
          <span
            className="chip"
            style={{
              flexShrink: 0,
              fontSize: 9,
              padding: "1px 6px",
              background: "var(--bg-3)",
              color: "var(--fg-2)",
            }}
          >
            {t("customFile.badge")}
          </span>
        )}
        {(errors > 0 || warnings > 0) && (
          <span
            className="mono shrink-0"
            style={{
              fontSize: 9.5,
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
              width: isKebabVisible ? 22 : 0,
              overflow: "hidden",
              pointerEvents: isKebabVisible ? "auto" : "none",
              transition: "opacity 0.1s",
            }}
            aria-label={t("customFile.replaceMenuItem")}
          >
            <MoreVertical size={12} />
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
              style={{ padding: "8px 12px", fontSize: 12.5 }}
              onSelect={() => {
                setUploadOpen(true);
              }}
            >
              <Upload size={12} />
              <span>{t("customFile.replaceMenuItem")}</span>
            </DropdownMenu.Item>
            {isCustom && (
              <DropdownMenu.Item
                className={clsx(
                  "flex cursor-pointer select-none items-center gap-2 outline-none",
                  "focus:bg-bg-hover",
                )}
                style={{ padding: "8px 12px", fontSize: 12.5 }}
                onSelect={() => {
                  setRevertConfirmOpen(true);
                }}
              >
                <RefreshCw size={12} />
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
                  style={{ padding: "8px 12px", fontSize: 12.5 }}
                >
                  <Download size={12} />
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
