import type { StatusDotStatus } from "@shared/ui";
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

/** Тон состояния задачи: точка той же формы и цвета, что у раннеров и сервисов. */
export const JOB_TONE: Record<JobState, StatusDotStatus> = {
  queued: "neutral",
  running: "info",
  succeeded: "success",
  failed: "danger",
  cancelled: "neutral",
  timed_out: "warning",
};

/** Выполняющиеся задачи по раннерам: сколько мест у каждого занято. */
export const busySlots = (
  jobs: readonly Pick<AdminJob, "status" | "runner_id">[],
): ReadonlyMap<string, number> => {
  const map = new Map<string, number>();
  for (const job of jobs) {
    if (job.status !== "running" || job.runner_id === null) continue;
    map.set(job.runner_id, (map.get(job.runner_id) ?? 0) + 1);
  }
  return map;
};

/** Сколько задача выполнялась или выполняется, секунды; null, если не начиналась. */
export const runSeconds = (job: AdminJob, now: number): number | null => {
  if (job.started_at === null) return null;
  const start = Date.parse(job.started_at);
  const end = job.finished_at === null ? now : Date.parse(job.finished_at);
  if (Number.isNaN(start) || Number.isNaN(end)) return null;
  return Math.max(0, Math.round((end - start) / 1000));
};
