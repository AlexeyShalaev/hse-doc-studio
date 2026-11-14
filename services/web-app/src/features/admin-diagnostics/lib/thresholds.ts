import type { DiagThreshold } from "@entities/session";

/** Единицы и порядок показа порогов; пары «предупреждение / сбой» стоят рядом. */
export const THRESHOLD_GROUPS = [
  { id: "database", names: ["db_latency_warn_ms", "db_latency_fail_ms"] },
  { id: "store", names: ["store_latency_warn_ms", "store_latency_fail_ms"] },
  { id: "queue", names: ["queue_wait_warn_s", "queue_wait_fail_s"] },
  { id: "stuck", names: ["stuck_job_warn_s", "stuck_job_fail_s"] },
  { id: "tls", names: ["tls_warn_days", "tls_fail_days"] },
  { id: "backups", names: ["backup_warn_hours", "backup_fail_hours"] },
  {
    id: "mail",
    names: ["mail_failed_warn_percent", "mail_failed_fail_percent"],
  },
  { id: "alerts", names: ["confirm_runs", "repeat_hours"] },
] as const;

export type Draft = Record<string, string>;

export const draftOf = (thresholds: DiagThreshold[]): Draft =>
  Object.fromEntries(thresholds.map((th) => [th.name, String(th.value)]));

export const defaultsDraft = (thresholds: DiagThreshold[]): Draft =>
  Object.fromEntries(thresholds.map((th) => [th.name, String(th.default)]));

/** Имена порогов, значение которых вне границ или не целое. */
export const outOfRange = (
  draft: Draft,
  thresholds: DiagThreshold[],
): string[] =>
  thresholds
    .filter((th) => {
      const n = Number(draft[th.name]);
      return !Number.isInteger(n) || n < th.min || n > th.max;
    })
    .map((th) => th.name);

/** Пары, нарушившие порядок: предупреждение раньше сбоя, у TLS за больше дней до конца срока. */
export const misordered = (draft: Draft): string[] => {
  const n = (name: string) => Number(draft[name]);
  const bad: string[] = [];
  for (const g of THRESHOLD_GROUPS) {
    const [warn, fail] = g.names;
    if (
      g.id === "alerts" ||
      draft[warn] === undefined ||
      draft[fail] === undefined
    )
      continue;
    const ok = g.id === "tls" ? n(warn) > n(fail) : n(warn) < n(fail);
    if (!ok) bad.push(warn, fail);
  }
  return bad;
};

export const bodyOf = (draft: Draft): Record<string, number> =>
  Object.fromEntries(Object.entries(draft).map(([k, v]) => [k, Number(v)]));
