import {
  Ban,
  CheckCircle2,
  Circle,
  CircleSlash,
  Clock,
  TriangleAlert,
  X,
  XCircle,
} from "lucide-react";
import { useTranslation } from "react-i18next";
import { Button, ProgressBar, Spinner } from "@shared/ui";
import type { DiskStep, RunnerDiskCommand } from "../model/runnerDisk.schema";
import {
  diskCommandPhase,
  diskCommandProgress,
  isDiskCommandActive,
  type RunnerDiskCommandPhase,
} from "../lib/runnerDiskLib";
import { diskSize, diskWhen } from "./format";

// Ход и итог очистки (4.1): «Ждём раннер», шаги с отметками, «Остановить после текущего шага»,
// итог «Освобождено N» или причина, почему не вышло.

const StepIcon = ({
  status,
  active,
}: {
  status: DiskStep["status"];
  active: boolean;
}) => {
  switch (status) {
    case "running":
      // Команда закрылась, а шаг так и остался «идёт»: раннер пропал посреди шага.
      return active ? (
        <Spinner size="sm" />
      ) : (
        <TriangleAlert size="0.8125rem" style={{ color: "var(--c-warn)" }} />
      );
    case "done":
      return <CheckCircle2 size="0.8125rem" style={{ color: "var(--c-ok)" }} />;
    case "error":
      return <XCircle size="0.8125rem" style={{ color: "var(--c-err)" }} />;
    case "skipped":
      return <CircleSlash size="0.8125rem" style={{ color: "var(--fg-3)" }} />;
    default:
      return <Circle size="0.8125rem" style={{ color: "var(--fg-3)" }} />;
  }
};

const PhaseIcon = ({ phase }: { phase: RunnerDiskCommandPhase }) => {
  switch (phase) {
    case "waiting":
      return <Clock size="0.875rem" style={{ color: "var(--fg-2)" }} />;
    case "running":
    case "cancelling":
      return <Spinner size="sm" />;
    case "done":
    case "nothing":
      return <CheckCircle2 size="0.875rem" style={{ color: "var(--c-ok)" }} />;
    case "cancelled":
      return <Ban size="0.875rem" style={{ color: "var(--fg-2)" }} />;
    case "error":
      return <XCircle size="0.875rem" style={{ color: "var(--c-err)" }} />;
    case "expired":
    case "lost":
      return (
        <TriangleAlert size="0.875rem" style={{ color: "var(--c-warn)" }} />
      );
  }
};

const BORDER: Record<RunnerDiskCommandPhase, string> = {
  waiting: "var(--accent-line)",
  running: "var(--accent-line)",
  cancelling: "var(--accent-line)",
  done: "var(--border)",
  nothing: "var(--border)",
  cancelled: "var(--border)",
  error: "var(--c-err)",
  expired: "var(--c-warn)",
  lost: "var(--c-warn)",
};

const FINISHED: ReadonlySet<DiskStep["status"]> = new Set([
  "done",
  "error",
  "skipped",
]);

const StepRow = ({ step, active }: { step: DiskStep; active: boolean }) => {
  const { t } = useTranslation("runnerDisk");
  const named = step.kind === "image" || step.kind === "container";
  const label = named ? (step.ref ?? "") : t(`job.step.${step.kind}`);
  return (
    <li
      className="flex flex-col"
      style={{ gap: "0.125rem", fontSize: "0.71875rem", minWidth: 0 }}
      data-status={step.status}
    >
      <span className="flex items-center" style={{ gap: "0.5rem" }}>
        <span style={{ flexShrink: 0, display: "flex" }}>
          <StepIcon status={step.status} active={active} />
        </span>
        <span
          className={named ? "mono" : undefined}
          style={{
            minWidth: 0,
            flex: 1,
            overflow: "hidden",
            textOverflow: "ellipsis",
            whiteSpace: "nowrap",
            color: step.status === "skipped" ? "var(--fg-3)" : "var(--fg-1)",
          }}
          title={label}
        >
          {label}
        </span>
        {step.status === "done" && step.freed_bytes > 0 && (
          <span className="mono dim" style={{ flexShrink: 0 }}>
            {diskSize(step.freed_bytes)}
          </span>
        )}
      </span>
      {step.error && (
        <span
          style={{
            paddingLeft: "1.3125rem",
            color: "var(--c-err)",
            overflowWrap: "anywhere",
          }}
        >
          {step.error}
        </span>
      )}
    </li>
  );
};

export const RunnerDiskJob = ({
  command,
  cancelling,
  onCancel,
  onHide,
}: {
  command: RunnerDiskCommand;
  /** Запрос остановки уже ушёл. */
  cancelling: boolean;
  onCancel: () => void;
  /** Скрыть итог закрытой команды; у идущей кнопки нет. */
  onHide?: (() => void) | undefined;
}) => {
  const { t } = useTranslation("runnerDisk");
  const phase = diskCommandPhase(command);
  const active = isDiskCommandActive(command);
  const { n, total, freed } = diskCommandProgress(command);
  const size = diskSize(freed);
  const steps = command.progress?.steps ?? [];
  const title = {
    waiting: t("job.waiting"),
    running: t("job.running", { n, total, size }),
    cancelling: t("job.cancelling", { size }),
    done: t("job.done", { size }),
    nothing: t("job.nothing"),
    error: t("job.error", { size }),
    cancelled: t("job.cancelled", { size }),
    expired: t("job.expired"),
    lost: t("job.lost"),
  }[phase];
  const when = diskWhen(command.created_at);
  return (
    <section
      data-testid="runner-disk-job"
      data-phase={phase}
      aria-live="polite"
      className="flex flex-col"
      style={{
        gap: "0.5rem",
        padding: "0.75rem",
        borderRadius: "var(--r-3)",
        border: `1px solid ${BORDER[phase]}`,
        background: "var(--bg-1)",
      }}
    >
      <div className="flex items-start" style={{ gap: "0.5rem" }}>
        <span
          style={{ flexShrink: 0, display: "flex", marginTop: "0.0625rem" }}
        >
          <PhaseIcon phase={phase} />
        </span>
        <span className="flex flex-col" style={{ flex: 1, minWidth: 0 }}>
          <span
            data-testid="runner-disk-job-title"
            style={{ fontSize: "0.8125rem", fontWeight: 600, lineHeight: 1.4 }}
          >
            {title}
          </span>
          <span className="dim" style={{ fontSize: "0.6875rem" }}>
            {command.created_by
              ? t("job.startedBy", { name: command.created_by.name, when })
              : t("job.startedAt", { when })}
          </span>
        </span>
        {!active && onHide && (
          <button
            type="button"
            className="icon-btn"
            aria-label={t("job.hide")}
            title={t("job.hide")}
            onClick={onHide}
          >
            <X size="0.75rem" aria-hidden="true" />
          </button>
        )}
      </div>

      {active && (
        <ProgressBar
          percent={
            phase === "waiting" || total === 0
              ? null
              : (steps.filter((s) => FINISHED.has(s.status)).length / total) *
                100
          }
          label={t("job.progress")}
        />
      )}

      {steps.length > 0 && (
        <ol
          className="flex flex-col"
          style={{
            gap: "0.25rem",
            margin: 0,
            padding: 0,
            listStyle: "none",
            maxHeight: "12rem",
            overflow: "auto",
          }}
        >
          {steps.map((step, index) => (
            <StepRow
              key={`${step.kind}-${step.ref ?? String(index)}`}
              step={step}
              active={active}
            />
          ))}
        </ol>
      )}

      {command.progress?.error && (
        <div style={{ fontSize: "0.71875rem", color: "var(--c-err)" }}>
          {command.progress.error}
        </div>
      )}

      {active && (
        <Button
          type="button"
          size="sm"
          variant="secondary"
          style={{ alignSelf: "flex-start" }}
          disabled={cancelling || phase === "cancelling"}
          onClick={onCancel}
          data-testid="runner-disk-cancel"
        >
          <Ban size="0.75rem" aria-hidden="true" />
          {phase === "waiting" ? t("job.cancelWaiting") : t("job.cancel")}
        </Button>
      )}
    </section>
  );
};
