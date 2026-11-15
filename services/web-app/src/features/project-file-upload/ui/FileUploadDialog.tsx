import { useState } from "react";
import { useTranslation } from "react-i18next";
import { AlertTriangle, CheckCircle2 } from "lucide-react";
import { formatFileSize } from "@shared/lib/formatFileSize";
import { Modal } from "@shared/ui/Modal";
import { ProgressBar } from "@shared/ui/ProgressBar";
import { Spinner } from "@shared/ui/Spinner";
import type { FailureReason, UploadOutcome } from "../lib/uploadOutcome";
import type { FileUploadController } from "../model/useProjectFileUpload";

export type FileUploadDialogProps = {
  upload: FileUploadController;
};

const pathStyle = {
  fontSize: "0.71875rem",
  wordBreak: "break-all",
} as const;

const useReasonText = (): ((reason: FailureReason) => string) => {
  const { t } = useTranslation("fileUpload");
  return (reason) => {
    if (reason.code === "server") return reason.detail ?? t("reason.server");
    if (reason.bytes !== undefined) {
      return t(`reason.${reason.code}WithSize`, {
        size: formatFileSize(reason.bytes),
      });
    }
    return t(`reason.${reason.code}`);
  };
};

type SummaryProps = { outcomes: readonly UploadOutcome[] };

const Summary = ({ outcomes }: SummaryProps) => {
  const { t } = useTranslation("fileUpload");
  const reasonText = useReasonText();
  const uploaded = outcomes.filter((o) => o.status === "uploaded").length;
  const skipped = outcomes.filter((o) => o.status === "skipped").length;
  const failed = outcomes.filter(
    (o): o is Extract<UploadOutcome, { status: "failed" }> =>
      o.status === "failed",
  );
  return (
    <div className="flex flex-col" style={{ gap: "0.75rem" }}>
      <div className="flex items-center" style={{ gap: "0.5rem" }}>
        {uploaded > 0 ? (
          <CheckCircle2
            size="0.9375rem"
            style={{ color: "var(--c-ok)", flexShrink: 0 }}
          />
        ) : (
          <AlertTriangle
            size="0.9375rem"
            style={{ color: "var(--c-warn)", flexShrink: 0 }}
          />
        )}
        <span style={{ fontSize: "0.8125rem", color: "var(--fg-1)" }}>
          {t("summary.uploaded", { count: uploaded, total: outcomes.length })}
          {skipped > 0 && ` ${t("summary.skipped", { count: skipped })}`}
        </span>
      </div>
      {failed.length > 0 && (
        <div className="flex flex-col" style={{ gap: "0.375rem" }}>
          <span className="dim" style={{ fontSize: "0.75rem" }}>
            {t("summary.failedTitle", { count: failed.length })}
          </span>
          <ul
            className="flex flex-col"
            data-testid="upload-failures"
            style={{
              gap: "0.375rem",
              margin: 0,
              padding: 0,
              listStyle: "none",
              maxHeight: "16rem",
              overflowY: "auto",
            }}
          >
            {failed.map((item) => (
              <li
                key={item.path}
                className="flex flex-col"
                style={{
                  gap: "0.125rem",
                  padding: "0.375rem 0.5rem",
                  borderRadius: "var(--r-2)",
                  background: "var(--bg-2)",
                }}
              >
                <span className="mono" style={pathStyle}>
                  {item.path}
                </span>
                <span style={{ fontSize: "0.75rem", color: "var(--c-err)" }}>
                  {reasonText(item.reason)}
                </span>
              </li>
            ))}
          </ul>
        </div>
      )}
    </div>
  );
};

/**
 * Окно загрузки файлов в проект и скрытые поля выбора. Само окно видно, пока идёт подготовка,
 * вопрос о совпадающем имени, отправка или есть итог с отказами; удачная загрузка
 * заканчивается тостом без окна.
 */
export const FileUploadDialog = ({ upload }: FileUploadDialogProps) => {
  const { t } = useTranslation("fileUpload");
  const { state, bindFilesInput, bindFolderInput, onInputChange } = upload;
  const [applyToAll, setApplyToAll] = useState(false);
  const answer = (choice: "replace" | "keep_both" | "skip"): void => {
    upload.answerConflict(choice, applyToAll);
    // Галочка живёт один вопрос: с «применить ко всем» следующих вопросов не будет.
    setApplyToAll(false);
  };

  const footer = (() => {
    switch (state.phase) {
      case "conflict":
        return (
          <>
            <button type="button" className="btn" onClick={upload.cancel}>
              {t("conflict.cancel")}
            </button>
            <span style={{ flex: 1 }} />
            <button
              type="button"
              className="btn"
              onClick={() => {
                answer("skip");
              }}
            >
              {t("conflict.skip")}
            </button>
            <button
              type="button"
              className="btn"
              onClick={() => {
                answer("keep_both");
              }}
            >
              {t("conflict.keepBoth")}
            </button>
            <button
              type="button"
              className="btn primary"
              autoFocus
              onClick={() => {
                answer("replace");
              }}
            >
              {t("conflict.replace")}
            </button>
          </>
        );
      case "uploading":
        return (
          <button type="button" className="btn" onClick={upload.cancel}>
            {t("progress.stop")}
          </button>
        );
      case "done":
        return (
          <button
            type="button"
            className="btn primary"
            autoFocus
            onClick={upload.close}
          >
            {t("summary.close")}
          </button>
        );
      default:
        return null;
    }
  })();

  const title =
    state.phase === "conflict"
      ? t("conflict.title")
      : state.phase === "done"
        ? t("summary.title")
        : t("progress.title");

  const body = (() => {
    if (state.phase === "preparing") {
      return (
        <div className="flex items-center" style={{ gap: "0.5rem" }}>
          <Spinner size="sm" />
          <span className="dim" style={{ fontSize: "0.8125rem" }}>
            {t("preparing")}
          </span>
        </div>
      );
    }
    if (state.phase === "conflict" && state.conflict) {
      const { path, left } = state.conflict;
      return (
        <div className="flex flex-col" style={{ gap: "0.625rem" }}>
          <span style={{ fontSize: "0.8125rem", color: "var(--fg-1)" }}>
            {t("conflict.text")}
          </span>
          <span className="mono dim" style={pathStyle}>
            {path}
          </span>
          {left > 1 && (
            <label
              className="flex items-center"
              style={{ gap: "0.5rem", fontSize: "0.8125rem" }}
            >
              <input
                type="checkbox"
                checked={applyToAll}
                onChange={(event) => {
                  setApplyToAll(event.target.checked);
                }}
              />
              {t("conflict.applyToAll", { count: left })}
            </label>
          )}
        </div>
      );
    }
    if (state.phase === "uploading" && state.progress) {
      const { index, total, path, percent } = state.progress;
      return (
        <div className="flex flex-col" style={{ gap: "0.5rem" }}>
          <span className="dim" style={{ fontSize: "0.75rem" }}>
            {t("progress.counter", { index, total })}
          </span>
          <span className="mono" style={pathStyle}>
            {path}
          </span>
          <ProgressBar percent={percent} label={t("progress.title")} />
        </div>
      );
    }
    if (state.phase === "done") return <Summary outcomes={state.outcomes} />;
    return null;
  })();

  return (
    <>
      <input
        ref={bindFilesInput}
        type="file"
        multiple
        hidden
        data-testid="file-upload-input"
        onChange={onInputChange}
      />
      <input
        ref={bindFolderInput}
        type="file"
        multiple
        hidden
        data-testid="folder-upload-input"
        onChange={onInputChange}
      />
      <Modal
        isOpen={state.phase !== "idle"}
        onClose={() => {
          if (state.phase === "conflict") upload.cancel();
          else if (state.phase === "done") upload.close();
        }}
        title={title}
        width={480}
        footer={
          footer && (
            <div
              className="flex items-center justify-end"
              style={{ gap: "0.5rem", width: "100%" }}
            >
              {footer}
            </div>
          )
        }
      >
        {body}
      </Modal>
    </>
  );
};
