import type { AdminRunner } from "@entities/session";

// Состояние раннера считается на клиенте по last_seen_at: раннер опрашивает сервер
// долгим запросом до 25 с, так что тишина дольше минуты уже подозрительна.
export const ONLINE_WITHIN_S = 60;
export const STALE_WITHIN_S = 300;

export type RunnerStatus =
  "online" | "stale" | "offline" | "paused" | "revoked";

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
