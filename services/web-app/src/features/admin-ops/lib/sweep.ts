import type {
  LifecycleSweep,
  LifecycleSweepPreview,
  LifecycleSweepStep,
} from "@entities/session";

// «Освободить место» (docs/design/storage-cleanup.md, 4.3 и 5.4): что показать по прогону и
// предпросмотру. Считает только то, что пришло с сервера; итоги removed_total и freed_bytes
// сервер уже сложил по шагам.

/** Потолок счёта предпросмотра (5.4): дальше «больше 100 000 записей». */
export const SWEEP_COUNT_CAP = 100_000;

/** Итог закрытого прогона виден в плашке под шапкой сутки после окончания. */
export const SWEEP_RECENT_MS = 24 * 3600_000;

/** Источники, которые чистят файлы, а не строки таблиц: счёт в файлах. */
const FILE_SOURCES: ReadonlySet<string> = new Set(["collab_state"]);
export const sweepUnit = (key: string): "rows" | "files" =>
  FILE_SOURCES.has(key) ? "files" : "rows";

export type SweepProgress = {
  /** Номер текущего источника с единицы; у закрытого прогона число пройденных. */
  n: number;
  total: number;
  /** Источник в работе; null, если прогон закрыт или ещё не взял следующий. */
  current: LifecycleSweepStep | null;
};

const PASSED: ReadonlySet<LifecycleSweepStep["status"]> = new Set([
  "done",
  "error",
]);

export const sweepProgress = (sweep: LifecycleSweep): SweepProgress => {
  const total = sweep.steps.length;
  const index = sweep.steps.findIndex((s) => s.status === "running");
  if (index >= 0) {
    return { n: index + 1, total, current: sweep.steps[index] ?? null };
  }
  const passed = sweep.steps.filter((s) => PASSED.has(s.status)).length;
  return { n: passed, total, current: null };
};

/** Хоть у одного источника кончился бюджет: остаток уйдёт на плановом тике. */
export const sweepHasMore = (sweep: LifecycleSweep): boolean =>
  sweep.steps.some((s) => s.more);

/** Освобождено на диске по шагу: уменьшение размера источника по его замеру (S11). */
export const stepFreedBytes = (step: LifecycleSweepStep): number =>
  step.bytes_before !== null && step.bytes_after !== null
    ? Math.max(0, step.bytes_before - step.bytes_after)
    : 0;

/** Шаг прерван перезапуском сервера (5.4): `error` с причиной `interrupted`. */
export const isInterruptedStep = (step: LifecycleSweepStep): boolean =>
  step.status === "error" && step.error === "interrupted";

/**
 * Показывать ли плашку прогона под шапкой: идущий всегда, закрытый сутки после окончания,
 * если его не скрыли крестиком.
 */
export const isSweepRecent = (sweep: LifecycleSweep, now: number): boolean => {
  if (sweep.status === "running" || sweep.status === "cancelling") return true;
  const end = Date.parse(sweep.finished_at ?? sweep.updated_at);
  return Number.isNaN(end) || now - end <= SWEEP_RECENT_MS;
};

/** Источники с потолком счёта: подсказка под списком предпросмотра. */
export const previewHasCap = (preview: LifecycleSweepPreview): boolean =>
  preview.sources.some((s) => s.capped);

/** Исключённые источники по причине, в порядке причин: одна строка на причину. */
export const EXCLUDED_REASONS = [
  "protected",
  "own_task",
  "on_write",
  "infra",
] as const;
export type ExcludedReason = (typeof EXCLUDED_REASONS)[number];

export const excludedByReason = (
  preview: LifecycleSweepPreview,
): [ExcludedReason, string[]][] =>
  EXCLUDED_REASONS.map((reason): [ExcludedReason, string[]] => [
    reason,
    preview.excluded.filter((e) => e.reason === reason).map((e) => e.key),
  ]).filter(([, keys]) => keys.length > 0);
