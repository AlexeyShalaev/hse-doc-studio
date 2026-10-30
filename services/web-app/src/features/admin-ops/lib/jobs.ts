import type { AdminJob, JobState } from "@entities/session";

export const JOB_STATES: readonly JobState[] = [
  "queued",
  "running",
  "succeeded",
  "failed",
  "cancelled",
  "timed_out",
];

export const JOB_KINDS = [
  "compile",
  "office.convert",
  "signature.verify_detached",
  "pack.submission",
] as const;

export const isActive = (job: Pick<AdminJob, "status">): boolean =>
  job.status === "queued" || job.status === "running";

/** После этого ожидания задача считается застрявшей: подсветка в таблице. */
export const LONG_WAIT_S = 120;

export const JOB_BADGE: Record<
  JobState,
  "subtle" | "info" | "success" | "error" | "warning"
> = {
  queued: "subtle",
  running: "info",
  succeeded: "success",
  failed: "error",
  cancelled: "subtle",
  timed_out: "warning",
};

/** Сколько задача выполнялась или выполняется, секунды; null, если не начиналась. */
export const runSeconds = (job: AdminJob, now: number): number | null => {
  if (job.started_at === null) return null;
  const start = Date.parse(job.started_at);
  const end = job.finished_at === null ? now : Date.parse(job.finished_at);
  if (Number.isNaN(start) || Number.isNaN(end)) return null;
  return Math.max(0, Math.round((end - start) / 1000));
};
