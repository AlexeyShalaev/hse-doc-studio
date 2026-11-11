import { useEffect } from "react";
import { openProblems, useDiagnosticsQuiet } from "@features/admin-diagnostics";
import { useInstanceSettings } from "@features/admin-install";
import { useMailLogSummary } from "@features/admin-mail-log";
import {
  diskTone,
  quietRunners,
  summarizeHealth,
  useRunnerSummary,
  useLifecycle,
  useServices,
  useStorage,
} from "@features/admin-ops";
import { useApprovalCount } from "@features/admin-users";

// Сведения для навигации админки: счётчики у пунктов и название установки.
// Живут в своём lazy-чанке вместе с запросами разделов, чтобы оболочка
// (admin-*.js) не тянула их код. Ничего не рисует, только сообщает значения.

export type NavCounterTone = "accent" | "warning" | "danger";
export type NavCounters = Partial<
  Record<
    | "users"
    | "runners"
    | "services"
    | "storage"
    | "data"
    | "diagnostics"
    | "mail",
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
  const approvals = useApprovalCount().data ?? 0;
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
  const dataLevel = useLifecycle().data?.level ?? "ok";
  // Принятые осознанно предупреждения точки не дают: считаем только открытые.
  const diag = useDiagnosticsQuiet().data;
  const problems = diag ? openProblems(diag) : [];
  const diagCount = problems.length;
  const diagFail = problems.some((c) => c.status === "fail");
  // Письма, которые не ушли за сутки (L14): «не отправлялось» без SMTP сюда не входит.
  const mailFailed = useMailLogSummary().data?.failed ?? 0;
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
    if (dataLevel !== "ok") {
      counters.data = {
        count: 0,
        tone: dataLevel === "critical" ? "danger" : "warning",
      };
    }
    if (diagCount > 0) {
      counters.diagnostics = {
        count: diagCount,
        tone: diagFail ? "danger" : "warning",
      };
    }
    if (mailFailed > 0) {
      counters.mail = { count: mailFailed, tone: "danger" };
    }
    onChange({
      counters,
      instanceName: name !== "" ? name : null,
      instanceHost: host,
    });
  }, [
    approvals,
    quiet,
    down,
    degraded,
    diskCritical,
    dataLevel,
    diagCount,
    diagFail,
    mailFailed,
    name,
    host,
    onChange,
  ]);

  return null;
};
