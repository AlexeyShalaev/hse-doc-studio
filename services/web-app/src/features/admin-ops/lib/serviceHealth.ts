import type { AdminService, ServiceStatus } from "@entities/session";

/**
 * Состояние сервиса так, как его видит администратор. Сервер считает раннеры
 * рабочими, пока на связи хоть один, но меньше половины в сети уже перебои:
 * «partial». Одно правило для страницы «Сервисы», сводки и навигации, чтобы
 * они не спорили друг с другом.
 */
export type ServiceHealth = ServiceStatus | "partial";

export const serviceHealth = (s: AdminService): ServiceHealth => {
  const few =
    s.kind === "runners" &&
    s.status === "ok" &&
    s.total !== null &&
    s.online !== null &&
    s.online * 2 < s.total;
  return few ? "partial" : s.status;
};

/** Тон точки состояния: перебои и частичная работа одинаково «warning». */
export const HEALTH_TONE: Record<
  ServiceHealth,
  "success" | "warning" | "danger" | "neutral"
> = {
  ok: "success",
  partial: "warning",
  degraded: "warning",
  down: "danger",
  unconfigured: "neutral",
};

export type HealthSummary = {
  ok: AdminService[];
  /** Перебои: degraded и partial. */
  warn: AdminService[];
  down: AdminService[];
  off: AdminService[];
};

export const summarizeHealth = (
  services: readonly AdminService[],
): HealthSummary => {
  const out: HealthSummary = { ok: [], warn: [], down: [], off: [] };
  for (const s of services) {
    const h = serviceHealth(s);
    if (h === "ok") out.ok.push(s);
    else if (h === "down") out.down.push(s);
    else if (h === "unconfigured") out.off.push(s);
    else out.warn.push(s);
  }
  return out;
};
