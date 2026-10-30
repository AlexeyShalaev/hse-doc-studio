import type { AdminRunner } from "@entities/session";
import { ONLINE_WITHIN_S, STALE_WITHIN_S, secondsSince } from "./runnerStatus";

/** Состояние личного раннера: сервер знает «выключен», остальное считаем как у общих. */
export type PersonalStatus =
  "online" | "stale" | "offline" | "paused" | "revoked" | "disabled";

export const personalStatus = (
  runner: AdminRunner,
  now: number,
): PersonalStatus => {
  if (runner.revoked) return "revoked";
  if (runner.status === "disabled") return "disabled";
  if (runner.paused) return "paused";
  const age = secondsSince(runner.last_seen_at, now);
  if (age === null) return "offline";
  if (age <= ONLINE_WITHIN_S) return "online";
  return age <= STALE_WITHIN_S ? "stale" : "offline";
};
