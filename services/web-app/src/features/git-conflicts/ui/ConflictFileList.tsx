import { useId, useRef, useState } from "react";
import { useTranslation } from "react-i18next";
import type { TFunction } from "i18next";
import { Check, ChevronDown, ChevronRight } from "lucide-react";
import type { ConflictFile } from "@entities/git-sync";
import {
  ActionTag,
  FileList,
  FileRowShell,
  type ConflictTone,
} from "@shared/ui/ConflictKit";
import type { DraftMap, FileProgress } from "../model/conflictModel";

export type ConflictFileListProps = {
  needs: ConflictFile[];
  auto: ConflictFile[];
  selectedPath: string | null;
  drafts: DraftMap;
  progressOf: (file: ConflictFile) => FileProgress;
  onSelect: (path: string) => void;
};

const AUTO_TONE: Record<string, ConflictTone> = {
  merged: "ok",
  take_theirs: "info",
  delete: "muted",
  binary_newest: "warn",
};

const sectionLabelStyle: React.CSSProperties = {
  margin: 0,
  fontSize: 10.5,
  letterSpacing: "0.12em",
  textTransform: "uppercase",
};

/** Метка состояния файла: значок и слова, не один цвет. */
const StatusMark = ({ resolved }: { resolved: boolean }) => {
  const { t } = useTranslation("gitConflicts");
  return (
    <span
      className="flex items-center justify-center"
      style={{
        width: 16,
        height: 16,
        borderRadius: "50%",
        flexShrink: 0,
        color: resolved ? "var(--accent-ink)" : "transparent",
        background: resolved ? "var(--c-ok)" : "transparent",
        border: resolved ? "none" : "2px solid var(--c-err)",
      }}
    >
      {resolved && <Check size={10} strokeWidth={3} aria-hidden="true" />}
      <span className="sr-only">
        {resolved ? t("row.resolved") : t("row.open")}
      </span>
    </span>
  );
};

const KindChip = ({ file }: { file: ConflictFile }) => {
  const { t } = useTranslation("gitConflicts");
  const kind =
    file.conflict_type === "deleted_by_us" ||
    file.conflict_type === "deleted_by_them"
      ? "delete"
      : file.kind;
  return (
    <span
      className="badge"
      style={{ fontSize: 10, flexShrink: 0, color: "var(--fg-2)" }}
    >
      {t(`kind.${kind}`, { defaultValue: kind })}
    </span>
  );
};

const progressLine = (
  file: ConflictFile,
  progress: FileProgress,
  isManual: boolean,
  t: TFunction<"gitConflicts">,
): string => {
  if (isManual) return t("row.manual");
  if (file.hunks > 0) {
    return t("row.hunks", {
      done: file.hunks - Math.min(progress.open, file.hunks),
      total: file.hunks,
    });
  }
  if (file.fields > 0) {
    return t("row.fields", {
      done: file.fields - Math.min(progress.open, file.fields),
      total: file.fields,
    });
  }
  return progress.resolved ? t("row.versionChosen") : t("row.versionNeeded");
};

/**
 * Список файлов слева: сверху те, где нужно решение, ниже (свёрнуто) всё, что
 * сервер решил сам. Стрелки, Home и End переходят между строками.
 */
export const ConflictFileList = ({
  needs,
  auto,
  selectedPath,
  drafts,
  progressOf,
  onSelect,
}: ConflictFileListProps) => {
  const { t } = useTranslation("gitConflicts");
  const [autoOpen, setAutoOpen] = useState(false);
  const autoId = useId();
  const rootRef = useRef<HTMLElement>(null);

  // Выбранный автоматический файл должен быть виден, даже если группу свернули.
  const showAuto = autoOpen || auto.some((f) => f.path === selectedPath);

  const handleKeyDown = (event: React.KeyboardEvent<HTMLElement>): void => {
    const keys = ["ArrowDown", "ArrowUp", "Home", "End"];
    if (!keys.includes(event.key)) return;
    const rows = Array.from(
      rootRef.current?.querySelectorAll<HTMLButtonElement>("[data-file-row]") ??
        [],
    );
    const current = rows.indexOf(document.activeElement as HTMLButtonElement);
    if (current < 0 || rows.length === 0) return;
    event.preventDefault();
    const next =
      event.key === "Home"
        ? 0
        : event.key === "End"
          ? rows.length - 1
          : Math.min(
              Math.max(current + (event.key === "ArrowDown" ? 1 : -1), 0),
              rows.length - 1,
            );
    rows[next]?.focus();
  };

  return (
    <nav
      ref={rootRef}
      aria-label={t("list.aria")}
      className="flex flex-col"
      style={{ gap: 14 }}
      onKeyDown={handleKeyDown}
    >
      <section className="flex flex-col" style={{ gap: 6 }}>
        <h3 className="mono dim" style={sectionLabelStyle}>
          {t("list.needs")} · {needs.length}
        </h3>
        {needs.length === 0 ? (
          <p className="dim" style={{ margin: 0, fontSize: 12 }}>
            {t("list.noneNeeded")}
          </p>
        ) : (
          <FileList maxHeight="none">
            {needs.map((file) => {
              const progress = progressOf(file);
              const draft = drafts[file.path];
              return (
                <FileRowShell
                  key={file.path}
                  path={file.path}
                  isSelected={file.path === selectedPath}
                  onSelect={() => {
                    onSelect(file.path);
                  }}
                  tag={<StatusMark resolved={progress.resolved} />}
                  trailing={<KindChip file={file} />}
                  childrenIndent={24}
                >
                  <span className="dim" style={{ fontSize: 11 }}>
                    {progressLine(file, progress, draft?.kind === "text", t)}
                  </span>
                </FileRowShell>
              );
            })}
          </FileList>
        )}
      </section>

      {auto.length > 0 && (
        <section className="flex flex-col" style={{ gap: 6 }}>
          <button
            type="button"
            className="flex items-center mono dim"
            aria-expanded={showAuto}
            aria-controls={autoId}
            onClick={() => {
              setAutoOpen((open) => !open);
            }}
            style={{
              ...sectionLabelStyle,
              gap: 4,
              background: "none",
              border: 0,
              padding: 0,
              cursor: "pointer",
              textAlign: "left",
            }}
          >
            {showAuto ? (
              <ChevronDown size={12} aria-hidden="true" />
            ) : (
              <ChevronRight size={12} aria-hidden="true" />
            )}
            {t("list.auto")} · {auto.length}
          </button>
          {showAuto && (
            <div id={autoId}>
              <FileList maxHeight="none">
                {auto.map((file) => (
                  <FileRowShell
                    key={file.path}
                    path={file.path}
                    isSelected={file.path === selectedPath}
                    onSelect={() => {
                      onSelect(file.path);
                    }}
                    tag={
                      <ActionTag
                        label={t(`auto.action.${file.action}`, {
                          defaultValue: file.action,
                        })}
                        tone={AUTO_TONE[file.action] ?? "muted"}
                        minWidth={92}
                      />
                    }
                  />
                ))}
              </FileList>
            </div>
          )}
        </section>
      )}
    </nav>
  );
};
