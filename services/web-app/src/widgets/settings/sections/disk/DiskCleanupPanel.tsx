import { useEffect, useRef } from "react";
import { useQueryClient } from "@tanstack/react-query";
import { Ban, CheckCircle2, Circle, CircleSlash, XCircle } from "lucide-react";
import { useTranslation } from "react-i18next";
import { Spinner } from "@shared/ui/Spinner";
import { formatBytes, toast } from "@shared/lib";
import {
  dockerSystemKeys,
  isJobActive,
  useCancelCleanup,
  useCleanupJob,
  type CleanupJob,
  type CleanupStep,
} from "@entities/docker-system";

const stepLabel = (
  step: CleanupStep,
  t: (key: string) => string,
): { label: string; mono: boolean } => {
  if (step.kind === "build_cache") {
    return { label: t("disk.stepBuildCache"), mono: false };
  }
  if (step.kind === "dangling_images") {
    return { label: t("disk.stepDangling"), mono: false };
  }
  return { label: step.ref ?? "", mono: true };
};

const StepIcon = ({ status }: { status: CleanupStep["status"] }) => {
  switch (status) {
    case "running":
      return <Spinner size="sm" />;
    case "done":
      return <CheckCircle2 size={13} style={{ color: "var(--c-ok)" }} />;
    case "error":
      return <XCircle size={13} style={{ color: "var(--c-err)" }} />;
    case "skipped":
      return <CircleSlash size={13} style={{ color: "var(--fg-3)" }} />;
    default:
      return <Circle size={13} style={{ color: "var(--fg-3)" }} />;
  }
};

const JOB_TITLE_KEY: Record<CleanupJob["status"], string> = {
  running: "disk.jobRunning",
  cancelling: "disk.jobCancelling",
  done: "disk.jobDone",
  cancelled: "disk.jobCancelled",
  error: "disk.jobError",
};

/**
 * Live progress of the one cleanup job: a per-step checklist with freed sizes,
 * a running total and «Отменить» while active. When the job finishes it stays
 * on screen as the result summary until the next cleanup starts.
 */
export const DiskCleanupPanel = () => {
  const { t } = useTranslation("settings");
  const queryClient = useQueryClient();
  const jobQuery = useCleanupJob();
  const cancel = useCancelCleanup();

  const job = jobQuery.data?.job ?? null;
  const active = isJobActive(job);

  // Toast + usage refresh exactly once per finished job (poll ticks repeat the
  // same terminal snapshot, so the transition is tracked by job id).
  const notifiedJobRef = useRef<string | null>(null);
  useEffect(() => {
    if (!job || active || notifiedJobRef.current === job.id) return;
    notifiedJobRef.current = job.id;
    void queryClient.invalidateQueries({ queryKey: dockerSystemKeys.usage() });
    if (job.status === "error") {
      const firstError = job.steps.find((s) => s.error)?.error;
      toast.error(firstError ?? t("disk.jobError"));
      return;
    }
    if (job.freed_bytes > 0) {
      toast.success(
        t("disk.cleanupFreedToast", { size: formatBytes(job.freed_bytes) }),
      );
    } else if (job.status === "done") {
      toast.info(t("disk.cleanupNothingToast"));
    }
  }, [job, active, queryClient, t]);

  if (!job || job.steps.length === 0) return null;

  return (
    <div
      className="flex flex-col"
      style={{
        gap: 8,
        padding: 12,
        borderRadius: "var(--r-3)",
        border: active
          ? "1px solid var(--accent-line)"
          : "1px solid var(--border)",
        background: "var(--bg-1)",
      }}
    >
      <div className="flex items-center justify-between" style={{ gap: 8 }}>
        <div className="flex items-center" style={{ gap: 8 }}>
          {active ? (
            <Spinner size="sm" />
          ) : job.status === "done" ? (
            <CheckCircle2 size={14} style={{ color: "var(--c-ok)" }} />
          ) : job.status === "error" ? (
            <XCircle size={14} style={{ color: "var(--c-err)" }} />
          ) : (
            <Ban size={14} style={{ color: "var(--fg-2)" }} />
          )}
          <span style={{ fontSize: 12.5, fontWeight: 600 }}>
            {t(JOB_TITLE_KEY[job.status])}
          </span>
          {job.freed_bytes > 0 && (
            <span className="dim" style={{ fontSize: 11.5 }}>
              {t("disk.jobFreedSoFar", { size: formatBytes(job.freed_bytes) })}
            </span>
          )}
        </div>
        {active && (
          <button
            type="button"
            className="btn xs"
            disabled={cancel.isPending || job.status === "cancelling"}
            onClick={() => {
              cancel.mutate();
            }}
          >
            <Ban size={11} />
            {t("disk.jobCancel")}
          </button>
        )}
      </div>

      <div className="flex flex-col" style={{ gap: 4 }}>
        {job.steps.map((step, index) => {
          const { label, mono } = stepLabel(step, t);
          return (
            <div
              key={`${step.kind}-${step.ref ?? String(index)}`}
              className="flex items-center"
              style={{ gap: 8, fontSize: 11.5, minWidth: 0 }}
            >
              <span style={{ flexShrink: 0, display: "flex" }}>
                <StepIcon status={step.status} />
              </span>
              <span
                className={mono ? "mono" : undefined}
                style={{
                  minWidth: 0,
                  overflow: "hidden",
                  textOverflow: "ellipsis",
                  whiteSpace: "nowrap",
                  color:
                    step.status === "skipped" ? "var(--fg-3)" : "var(--fg-1)",
                }}
                title={label}
              >
                {label}
              </span>
              {step.status === "done" && step.freed_bytes > 0 && (
                <span
                  className="dim mono"
                  style={{ flexShrink: 0, fontSize: 10.5 }}
                >
                  −{formatBytes(step.freed_bytes)}
                </span>
              )}
              {step.error && (
                <span
                  style={{
                    flexShrink: 0,
                    fontSize: 10.5,
                    color: "var(--c-err)",
                  }}
                  title={step.error}
                >
                  {t("disk.stepFailed")}
                </span>
              )}
            </div>
          );
        })}
      </div>
    </div>
  );
};
