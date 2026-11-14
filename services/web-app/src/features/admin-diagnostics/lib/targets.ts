import type { DiagCheck } from "@entities/session";

/**
 * Куда вести из строки проверки, чтобы проблему можно было решать.
 * `key` это ключ подписи в словаре (`target.<key>`), `to` адрес раздела админки:
 * вкладка и фильтр в query-параметрах, #якорь на нужный раздел страницы.
 */
export type DiagTarget = { key: DiagTargetKey; to: string };

export type DiagTargetKey =
  | "runners"
  | "runnerToken"
  | "queue"
  | "queueStuck"
  | "queueWaiting"
  | "services"
  | "data"
  | "backups"
  | "backupDestinations"
  | "smtp"
  | "mail"
  | "instance";

export const TARGETS: Record<DiagTargetKey, string> = {
  runners: "/admin/runners",
  runnerToken: "/admin/runners?create=token",
  queue: "/admin/runners?tab=queue",
  queueStuck: "/admin/runners?tab=queue&state=running",
  queueWaiting: "/admin/runners?tab=queue&state=queued",
  services: "/admin/services",
  data: "/admin/data",
  backups: "/admin/backups",
  backupDestinations: "/admin/backups#backup-destinations",
  smtp: "/admin/settings#admin-smtp",
  // Журнал писем с фильтром «Не ушло» (docs/design/mail-log.md, V14).
  mail: "/admin/mail?status=failed",
  instance: "/admin/instance#admin-instance",
};

/**
 * Цель по умолчанию для каждой проверки сервера (CheckId в core/diagnostics).
 * null: решения в интерфейсе нет (база, миграции и планировщик чинятся на сервере),
 * строка остаётся обычным текстом. Новая проверка без записи здесь ломает тест.
 */
export const CHECK_TARGETS: Record<string, DiagTargetKey | null> = {
  database: null,
  migrations: null,
  object_storage: "services",
  disk: "data",
  runners: "runners",
  jobs: "queue",
  scheduler: null,
  tls_public: "instance",
  tls_s3: "services",
  backups: "backups",
  smtp: "smtp",
  mail_delivery: "mail",
};

/** Причины, которым нужна более точная цель, чем у проверки в целом. */
const REASON_TARGETS: Record<string, Record<string, DiagTargetKey>> = {
  runners: { no_runners: "runnerToken", no_online_runner: "runners" },
  jobs: { jobs_stuck: "queueStuck", queue_wait: "queueWaiting" },
  backups: { backups_no_destination: "backupDestinations" },
};

export const targetKeyOf = (
  check: Pick<DiagCheck, "id" | "reason">,
): DiagTargetKey | null => {
  const base = CHECK_TARGETS[check.id] ?? null;
  if (base === null) return null;
  const byReason = check.reason
    ? REASON_TARGETS[check.id]?.[check.reason]
    : undefined;
  return byReason ?? base;
};

/** Цель строки проверки или null, если решения в интерфейсе нет. */
export const targetOf = (
  check: Pick<DiagCheck, "id" | "reason">,
): DiagTarget | null => {
  const key = targetKeyOf(check);
  return key ? { key, to: TARGETS[key] } : null;
};
