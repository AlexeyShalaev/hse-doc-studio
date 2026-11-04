import { useId } from "react";
import { useTranslation } from "react-i18next";
import { AlertTriangle, Check, GitMerge, Send, XCircle } from "lucide-react";
import type { ConflictSession } from "@entities/git-sync";
import { Spinner } from "@shared/ui/Spinner";
import { formatWhen } from "../lib/format";
import type { SessionProgress } from "../model/conflictModel";
import type { DraftSaveState } from "../model/useConflictDrafts";

export type ConflictHeaderProps = {
  session: ConflictSession;
  progress: SessionProgress;
  saveState: DraftSaveState;
  canComplete: boolean;
  isBusy: boolean;
  /** Решения уже отправлены на сервер и применяются. */
  isCompleting: boolean;
  onComplete: () => void;
  onAbort: () => void;
  onRetrySave: () => void;
};

const SideLine = ({
  label,
  when,
  message,
}: {
  label: string;
  when: string;
  message: string | null | undefined;
}) => (
  <div className="conflict-side">
    <span style={{ fontWeight: 600, color: "var(--fg-0)" }}>{label}</span>
    {when && <span className="dim mono">{when}</span>}
    {message && (
      <span className="dim truncate" title={message}>
        «{message}»
      </span>
    )}
  </div>
);

const SaveState = ({
  state,
  onRetry,
}: {
  state: DraftSaveState;
  onRetry: () => void;
}) => {
  const { t } = useTranslation("gitConflicts");
  return (
    <span
      className="conflict-save"
      role="status"
      aria-live="polite"
      data-state={state}
    >
      {(state === "dirty" || state === "saving") && (
        <>
          <Spinner size="sm" />
          {t("save.saving")}
        </>
      )}
      {state === "saved" && (
        <>
          <Check size="0.75rem" aria-hidden="true" />
          {t("save.saved")}
        </>
      )}
      {state === "error" && (
        <>
          <AlertTriangle size="0.75rem" aria-hidden="true" />
          {t("save.error")}
          <button type="button" className="btn xs" onClick={onRetry}>
            {t("save.retry")}
          </button>
        </>
      )}
    </span>
  );
};

/** Шапка экрана: что случилось, кто и когда менял, сколько осталось решить. */
export const ConflictHeader = ({
  session,
  progress,
  saveState,
  canComplete,
  isBusy,
  isCompleting,
  onComplete,
  onAbort,
  onRetrySave,
}: ConflictHeaderProps) => {
  const { t } = useTranslation("gitConflicts");
  const hintId = useId();
  const labelId = useId();
  const theirsAuthor = session.theirs.author;
  const percent =
    progress.total === 0 ? 100 : (progress.resolved / progress.total) * 100;

  return (
    <header className="conflict-header">
      <div className="conflict-title-row">
        <div
          className="flex items-center"
          style={{ gap: "0.75rem", minWidth: 0 }}
        >
          <div
            className="flex items-center justify-center shrink-0"
            style={{
              width: "2.375rem",
              height: "2.375rem",
              borderRadius: "0.625rem",
              background: "var(--c-err-soft)",
              color: "var(--c-err)",
            }}
          >
            <GitMerge size="1.125rem" aria-hidden="true" />
          </div>
          <div
            className="flex flex-col"
            style={{ gap: "0.125rem", minWidth: 0 }}
          >
            <h2
              style={{
                margin: 0,
                fontSize: "1.125rem",
                fontWeight: 600,
                letterSpacing: "-0.01em",
              }}
            >
              {t("title")}
            </h2>
            <p
              className="dim"
              style={{ margin: 0, fontSize: "0.78125rem", maxWidth: "40rem" }}
            >
              {t("subtitle")}
            </p>
          </div>
        </div>
        <div className="conflict-actions">
          <button
            type="button"
            className="btn"
            disabled={isBusy}
            onClick={onAbort}
          >
            <XCircle size="0.8125rem" aria-hidden="true" />
            {t("action.abort")}
          </button>
          <button
            type="button"
            className="btn primary"
            disabled={!canComplete}
            aria-describedby={canComplete ? undefined : hintId}
            onClick={onComplete}
          >
            {isCompleting ? (
              <Spinner size="sm" />
            ) : (
              <Send size="0.8125rem" aria-hidden="true" />
            )}
            {isCompleting ? t("action.completing") : t("action.complete")}
          </button>
        </div>
      </div>

      <div className="conflict-sides">
        <SideLine
          label={t("side.mine")}
          when={formatWhen(session.ours.at)}
          message={session.ours.message}
        />
        <SideLine
          label={t("side.theirs", {
            author: theirsAuthor ?? t("side.unknown"),
          })}
          when={formatWhen(session.theirs.at)}
          message={session.theirs.message}
        />
      </div>

      <div className="conflict-progress">
        <div className="flex items-center" style={{ gap: "0.75rem" }}>
          <span
            id={labelId}
            style={{
              fontSize: "0.75rem",
              fontWeight: 600,
              whiteSpace: "nowrap",
            }}
          >
            {t("progress.label", {
              done: progress.resolved,
              total: progress.total,
            })}
          </span>
          <div
            role="progressbar"
            aria-labelledby={labelId}
            aria-valuemin={0}
            aria-valuemax={progress.total}
            aria-valuenow={progress.resolved}
            className="conflict-bar"
          >
            <div
              className="conflict-bar-fill"
              style={{ width: `${String(percent)}%` }}
            />
          </div>
          <SaveState state={saveState} onRetry={onRetrySave} />
        </div>
        <span id={hintId} className="dim" style={{ fontSize: "0.71875rem" }}>
          {progress.open === 0
            ? t("progress.ready")
            : t("progress.left", { count: progress.openItems })}
        </span>
      </div>
    </header>
  );
};
