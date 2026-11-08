import type { AdminJob, AdminJobBatch, JobState } from "@entities/session";
import { JOB_STATES } from "./jobs";

/** Строка журнала очереди: одиночная задача или пакет «Собрать все» со своими задачами. */
export type QueueEntry =
  | { type: "job"; job: AdminJob }
  | {
      type: "batch";
      batch: AdminJobBatch;
      /** Первая (самая новая) задача пакета на экране: от неё проект и человек. */
      lead: AdminJob;
      /** Задачи пакета из загруженных страниц, в порядке журнала. */
      jobs: AdminJob[];
    };

/**
 * Собирает задачи одной команды «Собрать все» в одну строку пакета на месте самой
 * новой из них; одиночные задачи и пакет из одной задачи остаются как есть.
 * Задачи пакета могут идти вперемешку с чужими и расходиться по страницам: строка
 * пакета берёт все загруженные, а счёт по состояниям приходит от сервера целиком.
 */
export const groupQueue = (jobs: readonly AdminJob[]): QueueEntry[] => {
  const members = new Map<string, AdminJob[]>();
  for (const job of jobs) {
    if (!job.batch || job.batch.total < 2) continue;
    const list = members.get(job.batch.id);
    if (list) list.push(job);
    else members.set(job.batch.id, [job]);
  }
  const entries: QueueEntry[] = [];
  const placed = new Set<string>();
  for (const job of jobs) {
    const batch = job.batch;
    const list = batch ? members.get(batch.id) : undefined;
    if (!batch || !list) {
      entries.push({ type: "job", job });
      continue;
    }
    if (placed.has(batch.id)) continue;
    placed.add(batch.id);
    entries.push({ type: "batch", batch, lead: job, jobs: list });
  }
  return entries;
};

/** Сколько задач пакета ещё можно отменить: в очереди и идущие. */
export const batchActive = (batch: AdminJobBatch): number =>
  (batch.by_state.queued ?? 0) + (batch.by_state.running ?? 0);

/** Состояния пакета с ненулевым счётом в порядке журнала: «2 в очереди, 1 выполняется». */
export const batchStates = (
  batch: AdminJobBatch,
): { state: JobState; count: number }[] =>
  JOB_STATES.map((state) => ({
    state,
    count: batch.by_state[state] ?? 0,
  })).filter((row) => row.count > 0);

/** Тон точки пакета: идёт, ждёт, есть сбой или всё закончено. */
export const batchTone = (batch: AdminJobBatch): JobState => {
  const count = (state: JobState) => batch.by_state[state] ?? 0;
  if (count("running") > 0) return "running";
  if (count("queued") > 0) return "queued";
  if (count("failed") > 0) return "failed";
  if (count("timed_out") > 0) return "timed_out";
  if (count("succeeded") > 0) return "succeeded";
  return "cancelled";
};
