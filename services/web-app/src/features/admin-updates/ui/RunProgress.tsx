import {
  CheckCircle2,
  CircleDashed,
  Loader2,
  Minus,
  XCircle,
} from "lucide-react";
import { useTranslation } from "react-i18next";
import type { UpdateRun } from "../api/schemas";
import {
  buildProgress,
  elapsedSince,
  formatDuration,
  type Executor,
  type Progress,
  type StepState,
} from "../lib/progress";
import { useNow } from "../model/useNow";
import "./updates.css";

const STATE_ICON: Record<StepState, typeof CheckCircle2> = {
  pending: CircleDashed,
  active: Loader2,
  done: CheckCircle2,
  failed: XCircle,
  skipped: Minus,
};

const useUnits = () => {
  const { t } = useTranslation("adminUpdates");
  return {
    h: t("units.h"),
    min: t("units.min"),
    s: t("units.s"),
  };
};

export type ProgressStepsProps = {
  progress: Progress;
  run: UpdateRun;
  nowMs: number;
};

/**
 * Этапы обновления списком: у каждого значок и слово состояния (цвет не единственный признак), время и
 * подробность. Для идущего этапа подробность показывает, сколько он уже длится.
 */
export const ProgressSteps = ({ progress, run, nowMs }: ProgressStepsProps) => {
  const { t } = useTranslation("adminUpdates");
  const units = useUnits();
  return (
    <ol
      className="upd-steps"
      aria-label={t("progress.stepsLabel")}
      data-testid="update-steps"
    >
      {progress.steps.map((step) => {
        const Icon = STATE_ICON[step.state];
        const time =
          step.state === "active" && step.startedAt
            ? elapsedSince(step.startedAt, nowMs)
            : step.durationS;
        const showTime =
          time !== null &&
          step.state !== "pending" &&
          step.state !== "skipped" &&
          step.id !== "done";
        const timeText = showTime ? formatDuration(time, units) : null;
        return (
          <li
            key={step.id}
            className="upd-step"
            data-state={step.state}
            data-step={step.id}
            data-testid={`update-step-${step.id}`}
          >
            <Icon
              size="1rem"
              aria-hidden="true"
              className={
                step.state === "active"
                  ? "upd-step-icon upd-spin"
                  : "upd-step-icon"
              }
            />
            <span className="upd-step-title">
              {t(`step.${step.id}.title`)}
              <span className="upd-step-state">{t(`state.${step.state}`)}</span>
            </span>
            {timeText && <span className="upd-step-time">{timeText}</span>}
            <div className="upd-step-sub">
              {step.state === "active" && timeText && (
                <p className="upd-step-detail">
                  {t(`step.${step.id}.running`, { time: timeText })}
                </p>
              )}
              {step.id === "migrate" &&
                (run.from_revision !== null || run.to_revision !== null) &&
                step.state !== "pending" &&
                step.state !== "skipped" && (
                  <p className="upd-step-detail">
                    {t("progress.revisions", {
                      from: run.from_revision ?? "—",
                      to: run.to_revision ?? "—",
                    })}
                  </p>
                )}
              {step.message &&
                (step.state === "failed" || step.state === "active") && (
                  <p className="upd-step-detail">{step.message}</p>
                )}
            </div>
          </li>
        );
      })}
      {progress.recovery.map((r) => {
        const Icon = STATE_ICON[r.state];
        return (
          <li
            key={r.id}
            className="upd-step"
            data-state={r.state}
            data-step={r.id}
            data-testid={`update-step-${r.id}`}
          >
            <Icon
              size="1rem"
              aria-hidden="true"
              className={
                r.state === "active"
                  ? "upd-step-icon upd-spin"
                  : "upd-step-icon"
              }
            />
            <span className="upd-step-title">
              {t(`progress.recovery.${r.id}`)}
              <span className="upd-step-state">{t(`state.${r.state}`)}</span>
            </span>
            {r.durationS !== null && (
              <span className="upd-step-time">
                {formatDuration(r.durationS, units)}
              </span>
            )}
            {r.message && (
              <div className="upd-step-sub">
                <p className="upd-step-detail">{r.message}</p>
              </div>
            )}
          </li>
        );
      })}
    </ol>
  );
};

export type RunProgressCardProps = {
  run: UpdateRun;
  executor: Executor;
  /** Апдейтер давно не выходил на связь: исход запуска неизвестен. */
  updaterSilent: boolean;
  /** Сервер сейчас недоступен: данные на экране последние известные. */
  frozen?: boolean;
};

/** Карточка идущего обновления: заголовок, счётчик времени, этапы и строка для чтецов экрана (aria-live). */
export const RunProgressCard = ({
  run,
  executor,
  updaterSilent,
  frozen = false,
}: RunProgressCardProps) => {
  const { t } = useTranslation("adminUpdates");
  const units = useUnits();
  const nowMs = useNow(true);
  const progress = buildProgress(run, executor, nowMs);
  const total = elapsedSince(run.started_at ?? run.created_at, nowMs);
  const here = progress.position;
  const live = here
    ? t("progress.live", {
        index: here.index,
        total: here.total,
        step: t(`step.${here.id}.title`),
        state: t("state.active"),
      })
    : t(
        run.status === "waiting_backup"
          ? "progress.waitingBackup"
          : "progress.queued",
      );
  return (
    <div className="upd-card" data-testid="update-progress" data-tone="info">
      <div className="upd-card-head">
        <Loader2
          size="1.125rem"
          aria-hidden="true"
          className="upd-card-icon upd-spin"
        />
        <div style={{ minWidth: 0 }}>
          <h3 className="upd-card-title">
            {t("progress.heading", {
              kind: t(`history.kind.${run.kind}`),
              from: run.from_version,
              to: run.to_version,
            })}
          </h3>
          <p className="upd-live" role="status" aria-live="polite">
            {live}
          </p>
        </div>
      </div>
      <p className="upd-meta">
        <span data-testid="update-elapsed">
          {t("progress.elapsed", { time: formatDuration(total, units) })}
        </span>
        <span>{t("progress.keepOpen")}</span>
      </p>
      {(updaterSilent || frozen) && (
        <p
          className="upd-card-sub"
          role="alert"
          data-testid="update-progress-unknown"
        >
          {t(frozen ? "progress.frozen" : "progress.silent")}
        </p>
      )}
      <ProgressSteps progress={progress} run={run} nowMs={nowMs} />
    </div>
  );
};
