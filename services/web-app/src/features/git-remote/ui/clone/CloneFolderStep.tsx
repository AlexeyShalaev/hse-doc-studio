import { useId } from "react";
import { FolderOpen } from "lucide-react";
import { useTranslation } from "react-i18next";
import { useSharedFolder } from "@entities/git-remote";
import { Notice } from "@shared/ui/ConflictKit";
import { Spinner } from "@shared/ui/Spinner";
import { SharedFolderWarning } from "../SharedFolderWarning";
import { CloneStepLayout } from "./CloneStepLayout";

/** Окно выбора папки: его делает другая фича, поэтому его передаёт страница. */
export type CloneFolderPickerProps = {
  isOpen: boolean;
  onClose: () => void;
  onSelect: (path: string) => void;
  initialPath?: string | null;
};

export type FolderInspection = {
  /** Проверка папки закончилась с ответом (иначе: идёт или недоступна). */
  state: "idle" | "checking" | "ready" | "unavailable";
  exists?: boolean;
  isDir?: boolean;
  projectName?: string | null;
  hasProject?: boolean;
};

export type CloneFolderStepProps = {
  /** Что клонируем: «github.com/org/repo» или имя файла bundle. */
  sourceLabel: string;
  name: string;
  namePlaceholder: string;
  onNameChange: (value: string) => void;
  folder: string;
  onFolderChange: (value: string) => void;
  /** Нет окна выбора папки: остаётся ввод пути вручную. */
  onBrowse?: (() => void) | undefined;
  inspection: FolderInspection;
  /** Отказ запуска, который относится к папке (не пуста, проект уже открыт). */
  folderError: string | null;
  /** Общий отказ запуска. */
  startError: string | null;
  isStarting: boolean;
  onBack: () => void;
  onStart: () => void;
};

const InspectNote = ({
  inspection,
  hasFolder,
}: {
  inspection: FolderInspection;
  hasFolder: boolean;
}) => {
  const { t } = useTranslation("gitRemote");
  if (!hasFolder) {
    return (
      <p className="hint" style={{ margin: 0 }}>
        {t("clone.folder.inspect.empty")}
      </p>
    );
  }
  if (inspection.state === "checking") {
    return (
      <p
        className="hint flex items-center"
        style={{ margin: 0, gap: 6 }}
        role="status"
      >
        <Spinner size="sm" />
        {t("clone.folder.inspect.checking")}
      </p>
    );
  }
  if (inspection.state !== "ready") return null;
  if (inspection.exists === false) {
    return (
      <Notice tone="info" role="status" text={t("clone.folder.inspect.new")} />
    );
  }
  if (inspection.isDir === false) {
    return (
      <Notice tone="err" role="alert" text={t("clone.folder.inspect.notDir")} />
    );
  }
  if (inspection.hasProject) {
    return (
      <Notice
        tone="err"
        role="alert"
        text={
          inspection.projectName
            ? t("clone.folder.inspect.hasProject", {
                name: inspection.projectName,
              })
            : t("clone.folder.inspect.hasProjectUnnamed")
        }
      />
    );
  }
  return (
    <Notice
      tone="info"
      role="status"
      text={t("clone.folder.inspect.existing")}
    />
  );
};

// Шаг 2. Куда положить проект: название и папка. Папка проверяется сразу, до
// запуска, чтобы не ждать отказа сервера; но решает сервер (папка не пуста).
export const CloneFolderStep = ({
  sourceLabel,
  name,
  namePlaceholder,
  onNameChange,
  folder,
  onFolderChange,
  onBrowse,
  inspection,
  folderError,
  startError,
  isStarting,
  onBack,
  onStart,
}: CloneFolderStepProps) => {
  const { t } = useTranslation("gitRemote");
  const uid = useId();
  const nameId = `${uid}-name`;
  const nameHintId = `${uid}-name-hint`;
  const folderId = `${uid}-folder`;
  const folderHintId = `${uid}-folder-hint`;
  const trimmed = folder.trim();
  const sharedFolder = useSharedFolder(trimmed, trimmed !== "");

  // Папки может не быть вовсе: сервер тогда отвечает is_dir=false, но это не
  // «файл на месте папки», Студия создаст её сама.
  const blocked =
    inspection.state === "ready" &&
    inspection.exists !== false &&
    (inspection.isDir === false || inspection.hasProject === true);
  const canStart = trimmed !== "" && !blocked && !isStarting;

  return (
    <CloneStepLayout
      id="clone-folder"
      aria-label={t("clone.steps.folder")}
      onSubmit={(event) => {
        event.preventDefault();
        if (canStart) onStart();
      }}
      start={
        <button
          type="button"
          className="btn"
          onClick={onBack}
          disabled={isStarting}
        >
          {t("clone.back")}
        </button>
      }
      end={
        <button type="submit" className="btn primary" disabled={!canStart}>
          {isStarting && <Spinner size="sm" />}
          {t("clone.folder.clone")}
        </button>
      }
    >
      <div
        className="flex items-center"
        style={{
          gap: 8,
          padding: "8px 10px",
          borderRadius: "var(--r-2)",
          background: "var(--bg-2)",
          border: "1px solid var(--border)",
          fontSize: 12,
          minWidth: 0,
        }}
        data-testid="clone-source-summary"
      >
        <span className="dim">{t("clone.folder.source")}</span>
        <span
          className="mono truncate"
          style={{ minWidth: 0 }}
          title={sourceLabel}
        >
          {sourceLabel}
        </span>
      </div>

      <div className="field">
        <label htmlFor={nameId}>
          {t("clone.folder.name.label")}{" "}
          <span style={{ color: "var(--fg-3)", fontWeight: 400 }}>
            {t("clone.folder.name.optional")}
          </span>
        </label>
        <input
          id={nameId}
          type="text"
          className="input"
          value={name}
          placeholder={namePlaceholder || t("clone.folder.name.placeholder")}
          autoComplete="off"
          aria-describedby={nameHintId}
          onChange={(event) => {
            onNameChange(event.target.value);
          }}
        />
        <p id={nameHintId} className="hint" style={{ margin: 0 }}>
          {t("clone.folder.name.hint")}
        </p>
      </div>

      <div className="field">
        <label htmlFor={folderId}>{t("clone.folder.path.label")}</label>
        <div className="flex" style={{ gap: 8 }}>
          <input
            id={folderId}
            type="text"
            className="input mono"
            style={{ flex: 1, minWidth: 0 }}
            value={folder}
            autoFocus
            spellCheck={false}
            autoComplete="off"
            autoCapitalize="off"
            placeholder={t("clone.folder.path.placeholder")}
            aria-invalid={folderError !== null || blocked}
            aria-describedby={folderHintId}
            onChange={(event) => {
              onFolderChange(event.target.value);
            }}
          />
          {onBrowse && (
            <button type="button" className="btn" onClick={onBrowse}>
              <FolderOpen size={13} aria-hidden="true" />
              {t("clone.folder.path.browse")}
            </button>
          )}
        </div>
        <p id={folderHintId} className="hint" style={{ margin: 0 }}>
          {t("clone.folder.path.hint")}
        </p>
      </div>

      {folderError ? (
        <Notice tone="err" role="alert" text={folderError} />
      ) : (
        <InspectNote inspection={inspection} hasFolder={trimmed !== ""} />
      )}

      {sharedFolder.data?.detected && sharedFolder.data.provider && (
        <SharedFolderWarning provider={sharedFolder.data.provider} />
      )}

      {startError && <Notice tone="err" role="alert" text={startError} />}
    </CloneStepLayout>
  );
};
