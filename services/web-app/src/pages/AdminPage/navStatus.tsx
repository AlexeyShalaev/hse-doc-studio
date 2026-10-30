import { useEffect } from "react";
import { useInstanceSettings } from "@features/admin-install";
import {
  diskTone,
  quietRunners,
  summarizeHealth,
  useRunnerSummary,
  useServices,
  useStorage,
} from "@features/admin-ops";
import { useApprovals } from "@features/admin-users";

// Сведения для навигации админки: счётчики у пунктов и название установки.
// Живут в своём lazy-чанке вместе с запросами разделов, чтобы оболочка
// (admin-*.js) не тянула их код. Ничего не рисует, только сообщает значения.

export type NavCounterTone = "accent" | "warning" | "danger";
export type NavCounters = Partial<
  Record<
    "users" | "runners" | "services" | "storage",
    /** count 0: только точка, без числа (место на диске). */
    { count: number; tone: NavCounterTone }
  >
>;
export type NavStatus = {
  counters: NavCounters;
  instanceName: string | null;
  /** Хост публичного адреса: studio.example.org. */
  instanceHost: string | null;
};

const hostOf = (url: string): string | null => {
  try {
    return new URL(url).host || null;
  } catch {
    return null;
  }
};

export const NavStatusProbe = ({
  onChange,
}: {
  onChange: (status: NavStatus) => void;
}) => {
  const approvals = useApprovals(0).data?.total ?? 0;
  const runners = useRunnerSummary().data;
  const services = useServices().data;
  const instance = useInstanceSettings().data;

  // Счётчики сервера: раннеров может быть сколько угодно, список не читается.
  const quiet = runners ? quietRunners(runners) : 0;
  // То же правило, что на странице «Сервисы» и в сводке.
  const health = summarizeHealth(services ?? []);
  const down = health.down.length;
  const degraded = health.warn.length;
  const storage = useStorage().data;
  const diskCritical = storage ? diskTone(storage) === "danger" : false;
  const name = instance?.name.trim() ?? "";
  const host = instance ? hostOf(instance.public_url) : null;

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
    if (diskCritical) counters.storage = { count: 0, tone: "danger" };
    onChange({
      counters,
      instanceName: name !== "" ? name : null,
      instanceHost: host,
    });
  }, [approvals, quiet, down, degraded, diskCritical, name, host, onChange]);

  return null;
};
