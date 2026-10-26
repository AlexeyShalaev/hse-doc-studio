import { useRef } from "react";
import { useTranslation } from "react-i18next";
import type { TFunction } from "i18next";
import { Check } from "lucide-react";
import type { ConflictFile } from "@entities/git-sync";
import { FileList, FileRowShell } from "@shared/ui/ConflictKit";
import type { DraftMap, FileProgress } from "../model/conflictModel";
import { AutoMergedList } from "./AutoMergedList";

export type ConflictFileListProps = {
  needs: ConflictFile[];
  auto: ConflictFile[];
  selectedPath: string | null;
  drafts: DraftMap;
  progressOf: (file: ConflictFile) => FileProgress;
  onSelect: (path: string) => void;
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
  const rootRef = useRef<HTMLElement>(null);

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

      <AutoMergedList
        items={auto}
        selectedPath={selectedPath}
        onSelect={onSelect}
      />
    </nav>
  );
};
