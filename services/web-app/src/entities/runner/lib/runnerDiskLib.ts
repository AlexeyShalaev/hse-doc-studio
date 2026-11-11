import type {
  DiskTarget,
  RunnerDiskCommand,
  RunnerDiskCommandState,
  RunnerDiskReport,
  RunnerDiskView,
} from "../model/runnerDisk.schema";

// Правила диалога «Диск» без разметки (docs/design/storage-cleanup.md, 4.1 и 9.3): что
// показать, сколько освободится, когда опрашивать. Экраны W3–W6 берут их отсюда.

/** Опрос, пока команда не закрыта или идёт замер (9.3). */
export const RUNNER_DISK_ACTIVE_POLL_MS = 2_000;
/** Опрос при открытом диалоге, когда ничего не идёт. */
export const RUNNER_DISK_IDLE_POLL_MS = 30_000;

const ACTIVE_STATES: ReadonlySet<RunnerDiskCommandState> = new Set([
  "queued",
  "delivered",
  "running",
  "cancelling",
]);

/** Команда ещё не закрыта: раннер её не забрал, выполняет или останавливает. */
export const isDiskCommandActive = (
  command: RunnerDiskCommand | null | undefined,
): boolean => command != null && ACTIVE_STATES.has(command.state);

/** Нужен ли быстрый опрос вида: идёт очистка или стоит замер. */
export const isRunnerDiskBusy = (
  view: RunnerDiskView | null | undefined,
): boolean =>
  view != null && (view.measuring || isDiskCommandActive(view.command));

/**
 * Что показывает диалог по виду (4.1): заглушка старой версии, «замера ещё нет», полный
 * Docker-раннер, Docker недоступен, Kubernetes или локальная Студия.
 */
export type RunnerDiskMode =
  | "outdated"
  | "no_report"
  | "docker"
  | "docker_unavailable"
  | "kubernetes"
  | "desktop";

export const runnerDiskMode = (view: RunnerDiskView): RunnerDiskMode => {
  if (!view.supported) return "outdated";
  const report = view.report;
  if (report === null) return "no_report";
  if (report.docker_reason === "kubernetes") return "kubernetes";
  if (report.docker_reason === "managed_locally") return "desktop";
  if (!report.docker?.available) {
    return "docker_unavailable";
  }
  return "docker";
};

/**
 * Фаза полосы хода (4.1): ждём раннер, идёт, останавливается, итог (освобождено или нечего),
 * с ошибками, остановлено, не забрана, раннер пропал.
 */
export type RunnerDiskCommandPhase =
  | "waiting"
  | "running"
  | "cancelling"
  | "done"
  | "nothing"
  | "error"
  | "cancelled"
  | "expired"
  | "lost";

export const diskCommandPhase = (
  command: RunnerDiskCommand,
): RunnerDiskCommandPhase => {
  switch (command.state) {
    case "queued":
    case "delivered":
      return "waiting";
    case "done":
      return (command.progress?.freed_bytes ?? 0) > 0 ? "done" : "nothing";
    default:
      return command.state;
  }
};

/** Шаг {n} из {total} и сколько уже освобождено. */
export const diskCommandProgress = (
  command: RunnerDiskCommand,
): { n: number; total: number; freed: number; errors: number } => {
  const steps = command.progress?.steps ?? [];
  const started = steps.filter((s) => s.status !== "pending").length;
  return {
    n: Math.min(Math.max(started, 1), Math.max(steps.length, 1)),
    total: steps.length,
    freed: command.progress?.freed_bytes ?? 0,
    errors: steps.filter((s) => s.status === "error").length,
  };
};

const sum = (values: number[]): number =>
  values.reduce((acc, value) => acc + value, 0);

/** Кэш раннера целиком: кэш файлов и рабочие копии. */
export const runnerCacheBytes = (report: RunnerDiskReport): number =>
  report.cache.blobs.bytes + report.cache.workspaces.bytes;

/**
 * «Занято {used}, можно освободить {cleanable}» (4.1). Освободить можно `cleanable_bytes`
 * Docker-части и весь кэш раннера; тем же правилом сервер считает `cleanable_bytes` сводки и
 * поля `disk` в списках.
 */
export const runnerDiskTotals = (
  report: RunnerDiskReport,
): { used: number; cleanable: number } => {
  const docker = report.docker?.available ? report.docker : null;
  const cache = runnerCacheBytes(report);
  return {
    used: (docker?.total_bytes ?? 0) + cache,
    cleanable: (docker?.cleanable_bytes ?? 0) + cache,
  };
};

/**
 * Сколько освободит цель по последнему замеру: для подписей кнопок и подтверждений.
 * Откат (`rollback_bytes`) входит только с флажком.
 */
export const diskTargetBytes = (
  report: RunnerDiskReport,
  target: DiskTarget,
  includeRollback = false,
): number => {
  const docker = report.docker?.available ? report.docker : null;
  switch (target) {
    case "old_versions":
      return docker
        ? docker.old_versions.reclaimable_bytes +
            (includeRollback ? docker.old_versions.rollback_bytes : 0)
        : 0;
    case "unused_images":
      return docker ? sum(docker.unused_images.map((i) => i.size_bytes)) : 0;
    case "build_cache":
      return docker?.build_cache.reclaimable_bytes ?? 0;
    case "dangling_images":
      return docker?.dangling.bytes ?? 0;
    case "stopped_containers":
      return docker?.stopped_containers.bytes ?? 0;
    case "runner_cache":
      return runnerCacheBytes(report);
  }
};

/** Цели «Очистить всё»: всё, что раннер умеет сейчас; откат не входит (он отдельным флажком). */
export const cleanAllTargets = (report: RunnerDiskReport): DiskTarget[] => [
  ...report.targets,
];

/** Есть ли цель в последнем отчёте: иначе сервер ответит `disk_target_unavailable`. */
export const hasDiskTarget = (
  report: RunnerDiskReport | null,
  target: DiskTarget,
): boolean => report?.targets.includes(target) ?? false;
