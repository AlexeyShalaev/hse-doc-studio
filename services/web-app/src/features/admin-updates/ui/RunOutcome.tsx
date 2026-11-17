import {
  CheckCircle2,
  CircleAlert,
  CircleHelp,
  Undo2,
  XCircle,
} from "lucide-react";
import { useTranslation } from "react-i18next";
import { localeTag, reloadToNewBuild } from "@shared/lib";
import { Button, CopyField } from "@shared/ui";
import type { UpdateRun } from "../api/schemas";
import { isUnknownOutcome, reasonOf } from "../lib/failureReason";
import { buildProgress, formatDuration, type Executor } from "../lib/progress";
import { buildSupportText } from "../lib/support";
import { useNow } from "../model/useNow";
import "./updates.css";

const useUnits = () => {
  const { t } = useTranslation("adminUpdates");
  return { h: t("units.h"), min: t("units.min"), s: t("units.s") };
};

export type SuccessCardProps = {
  run: UpdateRun;
  /** Вкладка открыта на сборке старее установленной версии: предложить обновить страницу. */
  staleTab: boolean;
  tabVersion: string;
  /** Сколько секунд приложение было недоступно, если вкладка это видела. */
  outageS: number | null;
  notes: string[];
  onDismiss: () => void;
};

/** Итог успешного запуска: версия, время, заметки к релизу и, если нужно, «обновите страницу». */
export const SuccessCard = ({
  run,
  staleTab,
  tabVersion,
  outageS,
  notes,
  onDismiss,
}: SuccessCardProps) => {
  const { t } = useTranslation("adminUpdates");
  const units = useUnits();
  const at = run.finished_at
    ? new Date(run.finished_at).toLocaleString(localeTag())
    : "";
  return (
    <div className="upd-card" data-tone="ok" data-testid="update-success">
      <div className="upd-card-head">
        <CheckCircle2
          size="1.125rem"
          aria-hidden="true"
          className="upd-card-icon"
        />
        <div style={{ minWidth: 0 }}>
          <h3 className="upd-card-title" role="status">
            {t(`outcome.success.title.${run.kind}`, {
              version: run.to_version,
            })}
          </h3>
          <p className="upd-card-sub">
            {run.duration_s !== null
              ? t("outcome.success.body", {
                  time: formatDuration(run.duration_s, units),
                  at,
                })
              : at}
            {outageS !== null &&
              ` ${t("outcome.success.outage", { time: formatDuration(outageS, units) })}`}
          </p>
        </div>
      </div>
      {notes.length > 0 && (
        <div>
          <p className="upd-card-sub">{t("outcome.notes")}</p>
          <ul className="upd-notes" data-testid="update-success-notes">
            {notes.map((n) => (
              <li key={n}>{n}</li>
            ))}
          </ul>
        </div>
      )}
      {staleTab && (
        <p className="upd-card-sub" role="alert" data-testid="update-stale-tab">
          {t("outcome.staleTab", { tab: tabVersion, version: run.to_version })}
        </p>
      )}
      <div className="upd-actions">
        {staleTab && (
          <Button
            size="sm"
            data-testid="update-reload"
            onClick={() => void reloadToNewBuild()}
          >
            {t("outcome.reload")}
          </Button>
        )}
        <Button
          size="sm"
          variant="ghost"
          data-testid="update-outcome-dismiss"
          onClick={onDismiss}
        >
          {t("outcome.dismiss")}
        </Button>
      </div>
    </div>
  );
};

export type FailureCardProps = {
  run: UpdateRun;
  executor: Executor;
  appVersion: string;
  currentVersion: string;
  /** Повторить можно только обновление вперёд и только когда запуск возможен. */
  onRetry: (() => void) | undefined;
  onJournal: () => void;
  onDismiss?: (() => void) | undefined;
};

/**
 * Итог неудачного запуска: что случилось человеческим языком, что делать дальше, технические подробности
 * для поддержки в раскрывающемся блоке. Неизвестный исход назван неизвестным, а не успехом.
 */
export const FailureCard = ({
  run,
  executor,
  appVersion,
  currentVersion,
  onRetry,
  onJournal,
  onDismiss,
}: FailureCardProps) => {
  const { t } = useTranslation("adminUpdates");
  const nowMs = useNow(false);
  const reason = reasonOf(run.error_code, run.error);
  const unknown = isUnknownOutcome(reason);
  const Icon = unknown
    ? CircleHelp
    : run.status === "failed"
      ? XCircle
      : run.status === "cancelled"
        ? CircleAlert
        : Undo2;
  const tone = run.status === "failed" || unknown ? "err" : "warn";
  const titleKey = unknown ? "unknown" : run.status;
  const progress = buildProgress(run, executor, nowMs);
  const support = buildSupportText(run, executor, appVersion, progress);
  const failedStep = progress.steps.find((s) => s.state === "failed");
  return (
    <div
      className="upd-card"
      data-tone={tone}
      data-testid="update-failure-card"
      data-reason={reason}
    >
      <div className="upd-card-head">
        <Icon size="1.125rem" aria-hidden="true" className="upd-card-icon" />
        <div style={{ minWidth: 0 }}>
          <h3 className="upd-card-title" role="alert">
            {t(
              `outcome.${run.kind === "update" ? "failure" : "failureRollback"}.${titleKey}`,
              {
                to: run.to_version,
                from: run.from_version,
              },
            )}
          </h3>
          <p className="upd-card-sub" data-testid="update-failure-reason">
            <strong>{t(`reason.${reason}.title`)}.</strong>{" "}
            {t(`reason.${reason}.body`)}
          </p>
          {run.error && (
            <p className="upd-card-sub" data-testid="update-failure-message">
              {t("outcome.failure.message", { message: run.error })}
            </p>
          )}
          {failedStep && (
            <p className="upd-card-sub">
              {t("outcome.failure.atStep", {
                step: t(`step.${failedStep.id}.title`),
              })}
            </p>
          )}
          <p className="upd-card-sub" data-testid="update-failure-hint">
            <strong>{t("outcome.failure.next")}</strong>{" "}
            {t(`reason.${reason}.hint`)}
          </p>
          {run.db_restored && (
            <p className="upd-card-sub">{t("history.dbRestored")}</p>
          )}
          <p className="upd-card-sub" data-testid="update-failure-version">
            {t("outcome.failure.installed", { version: currentVersion })}
          </p>
        </div>
      </div>
      <details className="upd-details" data-testid="update-failure-details">
        <summary>{t("outcome.support")}</summary>
        <div className="upd-details-body">
          <p className="upd-card-sub">{t("outcome.supportHint")}</p>
          <CopyField
            value={support}
            label={t("outcome.supportCopy")}
            multiline
            wrap="spaces"
            rows={8}
          />
        </div>
      </details>
      <div className="upd-actions">
        {onRetry && (
          <Button size="sm" data-testid="update-retry" onClick={onRetry}>
            {t("outcome.retry", { version: run.to_version })}
          </Button>
        )}
        <Button
          size="sm"
          variant="ghost"
          data-testid="update-open-journal"
          onClick={onJournal}
        >
          {t("outcome.openJournal")}
        </Button>
        {onDismiss && (
          <Button
            size="sm"
            variant="ghost"
            data-testid="update-outcome-dismiss"
            onClick={onDismiss}
          >
            {t("outcome.dismiss")}
          </Button>
        )}
      </div>
    </div>
  );
};
