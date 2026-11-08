/**
 * Коды отказов, после которых LaTeX не запускался вовсе: нет Docker или образа, нет раннера, квота,
 * сбой подготовки проекта. Вывода сборки по ним нет, и интерфейс говорит об этом прямо.
 */
export const PRE_LAUNCH_CODES: ReadonlySet<string> = new Set([
  "image_missing",
  "docker_unavailable",
  "build_backend_unavailable",
  "no_runners",
  "no_runner_for_tags",
  "runner_paused",
  "runner_offline",
  "quota_exceeded",
  "staging_failed",
  "disk_full",
  "blob_unavailable",
  "restarted",
  "cancelled",
  "superseded",
  "job_lost",
]);

/**
 * Сборку оборвал перезапуск Студии или сервера, а продолжить её было нечем. Запись приходит со статусом
 * `cancelled` (не `failure`): документ тут ни при чём, и интерфейс называет её «прервана».
 */
export const INTERRUPTED_CODE = "interrupted";

/** Сборка прервана перезапуском, а не отменена человеком и не упала. */
export const isInterrupted = (
  status: string | null | undefined,
  code: string | null | undefined,
): boolean => status === "cancelled" && code === INTERRUPTED_CODE;

/** Первое предложение пояснения: короткая причина для строки списка, где полный текст не помещается. */
export const shortReason = (message: string): string => {
  const trimmed = message.trim();
  const match = /^.*?[.!?](?=\s|$)/s.exec(trimmed);
  return match ? match[0] : trimmed;
};

const SERVICE_LINE = /^\[(error|runner|queue|cancelled|stale)\]/;

/**
 * Есть ли в журнале вывод самой сборки, а не только служебные строки сервера и раннера
 * (`[error] …`, `[runner] …`). Пустой вывод при сбое значит: сборка не дошла до запуска.
 */
export const hasBuildOutput = (lines: readonly string[]): boolean =>
  lines.some((line) => line.trim() !== "" && !SERVICE_LINE.test(line));
