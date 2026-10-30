import { useEffect } from "react";
import { useInstanceSettings } from "@features/admin-install";
import {
  runnerStatus,
  useNow,
  useRunners,
  useServices,
} from "@features/admin-ops";
import { useApprovals } from "@features/admin-users";

// Сведения для навигации админки: счётчики у пунктов и название установки.
// Живут в своём lazy-чанке вместе с запросами разделов, чтобы оболочка
// (admin-*.js) не тянула их код. Ничего не рисует, только сообщает значения.

export type NavCounterTone = "accent" | "warning" | "danger";
export type NavCounters = Partial<
  Record<
    "users" | "runners" | "services",
    { count: number; tone: NavCounterTone }
  >
>;
export type NavStatus = { counters: NavCounters; instanceName: string | null };

export const NavStatusProbe = ({
  onChange,
}: {
  onChange: (status: NavStatus) => void;
}) => {
  const approvals = useApprovals(0).data?.total ?? 0;
  const runners = useRunners().data;
  const services = useServices().data;
  const instance = useInstanceSettings().data;
  const now = useNow();

  const quiet = (runners ?? []).filter((r) => {
    const status = runnerStatus(r, now);
    return status === "stale" || status === "offline";
  }).length;
  const down = (services ?? []).filter((s) => s.status === "down").length;
  const degraded = (services ?? []).filter(
    (s) => s.status === "degraded",
  ).length;
  const name = instance?.name.trim() ?? "";

  useEffect(() => {
    const counters: NavCounters = {};
    if (approvals > 0) counters.users = { count: approvals, tone: "accent" };
    if (quiet > 0) counters.runners = { count: quiet, tone: "warning" };
    if (down + degraded > 0) {
      counters.services = {
        count: down + degraded,
        tone: down > 0 ? "danger" : "warning",
      };
    }
    onChange({ counters, instanceName: name !== "" ? name : null });
  }, [approvals, quiet, down, degraded, name, onChange]);

  return null;
};
