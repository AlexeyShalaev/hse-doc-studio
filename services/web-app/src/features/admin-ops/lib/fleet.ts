import type { FleetItem, FleetRunner } from "@entities/session";

/** Раннер, который Студия не обновит сама: ему нужна подсказка, что сделать руками. */
export const isManual = (runner: FleetRunner): boolean =>
  runner.kind === "manual";

const SILENT_STATUSES: readonly string[] = ["offline", "stale"];

/** Не в сети или давно молчит: обновление не к чему подключать, поэтому по умолчанию он не выбран. */
export const isSilent = (runner: FleetRunner): boolean =>
  SILENT_STATUSES.includes(runner.status);

/** Что выбрано, пока админ ничего не менял: всё, что можно обновить отсюда и что на связи. */
export const defaultPicked = (items: readonly FleetRunner[]): Set<string> =>
  new Set(
    items
      .filter((item) => !isManual(item) && !isSilent(item))
      .map((item) => item.runner_id),
  );

export type FleetSummary = {
  total: number;
  done: number;
  skipped: number;
  failed: number;
  active: number;
};

/** Свод запуска: сколько обновлено, пропущено и упало, сколько ещё идёт или ждёт. */
export const summarize = (items: readonly FleetItem[]): FleetSummary => ({
  total: items.length,
  done: items.filter((i) => i.state === "succeeded").length,
  skipped: items.filter((i) => i.state === "skipped").length,
  failed: items.filter((i) => i.state === "failed").length,
  active: items.filter(
    (i) =>
      i.state === "pending" || i.state === "waiting" || i.state === "running",
  ).length,
});
