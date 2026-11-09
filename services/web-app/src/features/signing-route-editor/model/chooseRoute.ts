import { isRouteOpen, type SigningRouteSummary } from "@entities/signing-route";

export type RouteChoice =
  | { kind: "loading" }
  /** Править или показывать этот маршрут. */
  | { kind: "use"; id: string }
  /** Последний маршрут точки завершён: новый только по кнопке, он снимет этот с контроля. */
  | { kind: "completed"; id: string }
  /** Маршрута нет: создать черновик из пака. */
  | { kind: "create" };

/**
 * Какой маршрут точки открыть на экране автора. Список приходит новыми первыми. Открытый
 * (черновик, идёт, остановлен, возвращён) у точки один; отменённый открывается для «Отправить
 * заново»; завершённый не трогаем без явного «Новый маршрут». `wanted` (`?route=`) важнее.
 */
export const chooseRoute = (
  items: readonly SigningRouteSummary[] | undefined,
  wanted: string | null,
): RouteChoice => {
  if (!items) return { kind: "loading" };
  const asked =
    wanted === null ? undefined : items.find((r) => r.id === wanted);
  if (asked) return { kind: "use", id: asked.id };
  const open = items.find((r) => isRouteOpen(r.status));
  if (open) return { kind: "use", id: open.id };
  const latest = items.find((r) => r.status !== "archived");
  if (latest?.status === "cancelled") return { kind: "use", id: latest.id };
  if (latest?.status === "completed")
    return { kind: "completed", id: latest.id };
  return { kind: "create" };
};
