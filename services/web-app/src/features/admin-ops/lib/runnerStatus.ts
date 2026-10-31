import type { AdminRunner, AdminRunnerSummary } from "@entities/session";

// Состояние раннера считает сервер по last_seen_at (по нему же фильтр и порядок
// списка); здесь то же правило для галереи и проверок. Раннер опрашивает сервер
// долгим запросом до 25 с, так что тишина дольше минуты уже подозрительна.
export const ONLINE_WITHIN_S = 60;
export const STALE_WITHIN_S = 300;

// "disabled" — только у личных раннеров людей, когда личные раннеры выключены на
// установке; раннеры установки (эта таблица) этого состояния не знают.
export type RunnerStatus =
  "online" | "stale" | "offline" | "paused" | "revoked" | "disabled";

export const secondsSince = (
  iso: string | null,
  now: number,
): number | null => {
  if (iso === null) return null;
  const time = Date.parse(iso);
  return Number.isNaN(time)
    ? null
    : Math.max(0, Math.round((now - time) / 1000));
};

export const runnerStatus = (
  runner: AdminRunner,
  now: number,
): RunnerStatus => {
  if (runner.revoked) return "revoked";
  if (runner.paused) return "paused";
  const age = secondsSince(runner.last_seen_at, now);
  if (age === null) return "offline";
  if (age <= ONLINE_WITHIN_S) return "online";
  return age <= STALE_WITHIN_S ? "stale" : "offline";
};

/** Раннеры, которые могут взять задачу прямо сейчас. */
export const countOnline = (runners: readonly AdminRunner[], now: number) =>
  runners.filter((r) => runnerStatus(r, now) === "online").length;

/** Неотозванные раннеры по сводке сервера: в сети, затихшие, не в сети и на паузе. */
export const liveRunners = (s: AdminRunnerSummary): number =>
  s.online + s.paused + s.stale + s.offline;

/** Молчат без паузы: затихли или не в сети. */
export const quietRunners = (s: AdminRunnerSummary): number =>
  s.stale + s.offline;

/** Порядок состояний, как у сортировки сервера по status. */
export const RUNNER_STATUSES = [
  "online",
  "stale",
  "offline",
  "paused",
  "revoked",
] as const satisfies readonly RunnerStatus[];
