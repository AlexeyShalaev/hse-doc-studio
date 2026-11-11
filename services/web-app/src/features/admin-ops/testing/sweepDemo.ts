import { demoError, demoJson } from "@shared/api/demo";
import type { DemoResponse, DemoRoute } from "@shared/api/demo";
import type {
  LifecycleSweep,
  LifecycleSweepPreview,
  LifecycleSweepStep,
} from "@entities/session";
import { SWEEP_PREVIEWS } from "./sweepFixtures";

// Моки «Освободить место» поверх демо-транспорта (docs/design/storage-cleanup.md, 5.4 и 9.2):
// те же адреса, коды и переходы, что у сервера. Ход идёт по опросу: каждый GET прогона закрывает
// текущий источник и берёт следующий. Бэкенда (B7) ещё нет: на этих моках работает экран W6.

/** С чего начинается «Хранилище»: обычный предпросмотр, «нечего», с потолком. */
export type SweepDemoProfile = keyof typeof SWEEP_PREVIEWS;

export type LifecycleSweepDemoOptions = {
  /** null: не вошёл (401); `admin: false`: 404, как у админки. */
  getActor: () => { id: string; name: string; admin: boolean } | null;
  profile: () => SweepDemoProfile;
  now?: () => number;
};

export type LifecycleSweepDemo = {
  /** Маршруты клиента /api/admin. */
  routes: DemoRoute[];
  /** Положить прошлый прогон (например, `interrupted`), как будто он уже был. */
  seed: (sweep: LifecycleSweep | null) => void;
  reset: () => void;
};

const iso = (ms: number): string => new Date(ms).toISOString();
const isActive = (sweep: LifecycleSweep | null): sweep is LifecycleSweep =>
  sweep !== null &&
  (sweep.status === "running" || sweep.status === "cancelling");

export const createLifecycleSweepDemo = (
  options: LifecycleSweepDemoOptions,
): LifecycleSweepDemo => {
  const now = options.now ?? Date.now;
  let last: LifecycleSweep | null = null;
  /** После удачного прогона всё старше сроков удалено: предпросмотр «нечего». */
  let swept = false;
  let counter = 0;

  const guard = (): DemoResponse | null => {
    const actor = options.getActor();
    if (!actor) {
      return demoError(401, "auth_required", "Authentication required");
    }
    return actor.admin ? null : demoError(404, "not_found", "Not Found");
  };

  const preview = (): LifecycleSweepPreview => {
    const base = structuredClone(SWEEP_PREVIEWS[options.profile()]);
    if (!swept) return base;
    return {
      ...base,
      sources: base.sources.map((s) => ({ ...s, count: 0, capped: false })),
      nothing: true,
    };
  };

  const totals = (sweep: LifecycleSweep): LifecycleSweep => ({
    ...sweep,
    removed_total: sweep.steps.reduce((a, s) => a + s.removed, 0),
    freed_bytes: sweep.steps.reduce(
      (a, s) =>
        a +
        (s.bytes_before !== null && s.bytes_after !== null
          ? Math.max(0, s.bytes_before - s.bytes_after)
          : 0),
      0,
    ),
  });

  /** Один опрос: текущий источник закрывается, следующий начинается. */
  const advance = (sweep: LifecycleSweep): LifecycleSweep => {
    const sources = preview().sources;
    const steps = sweep.steps.map((s) => ({ ...s }));
    const current = steps.find((s) => s.status === "running");
    if (current) {
      const src = sources.find((s) => s.key === current.key);
      const removed = src?.count ?? 0;
      current.status = "done";
      current.removed = removed;
      // Партиции отбрасываются только у ai_usage: там место на диске действительно уходит.
      current.partitions_dropped =
        current.key === "ai_usage" && removed > 0 ? 2 : 0;
      const before = current.bytes_before ?? 0;
      current.bytes_after =
        current.key === "ai_usage" || current.key === "collab_state"
          ? Math.round(before * (removed > 0 ? 0.6 : 1))
          : before;
    }
    const t = iso(now());
    if (sweep.status === "cancelling") {
      for (const s of steps) if (s.status === "pending") s.status = "skipped";
      return totals({
        ...sweep,
        status: "cancelled",
        steps,
        updated_at: t,
        finished_at: t,
      });
    }
    const next = steps.find((s) => s.status === "pending");
    if (next) {
      next.status = "running";
      next.bytes_before =
        sources.find((s) => s.key === next.key)?.bytes ?? null;
      return totals({ ...sweep, steps, updated_at: t });
    }
    swept = true;
    return totals({
      ...sweep,
      status: "done",
      steps,
      updated_at: t,
      finished_at: t,
    });
  };

  const routes: DemoRoute[] = [
    {
      method: "GET",
      pattern: "/data-lifecycle/sweep/preview",
      handler: () => guard() ?? demoJson(preview()),
    },
    {
      method: "GET",
      pattern: "/data-lifecycle/sweep",
      handler: () => {
        const refused = guard();
        if (refused) return refused;
        if (isActive(last)) last = advance(last);
        return demoJson({ sweep: last });
      },
    },
    {
      method: "POST",
      pattern: "/data-lifecycle/sweep",
      handler: () => {
        const refused = guard();
        if (refused) return refused;
        if (isActive(last)) {
          return demoError(
            409,
            "lifecycle_sweep_busy",
            "A sweep is already running",
          );
        }
        const actor = options.getActor();
        const sources = preview().sources;
        const t = iso(now());
        counter += 1;
        const steps: LifecycleSweepStep[] = sources.map((s, index) => ({
          key: s.key,
          status: index === 0 ? "running" : "pending",
          removed: 0,
          partitions_dropped: 0,
          more: false,
          bytes_before: index === 0 ? s.bytes : null,
          bytes_after: null,
          error: null,
        }));
        last = {
          id: `lsw_demo_${String(counter).padStart(4, "0")}`,
          status: "running",
          started_by: actor ? { id: actor.id, name: actor.name } : null,
          started_at: t,
          updated_at: t,
          finished_at: null,
          steps,
          removed_total: 0,
          freed_bytes: 0,
        };
        return demoJson(last, 202);
      },
    },
    {
      method: "POST",
      pattern: "/data-lifecycle/sweep/:id/cancel",
      handler: (req) => {
        const refused = guard();
        if (refused) return refused;
        if (last === null || last.id !== req.params.id) {
          return demoError(404, "not_found", "Not Found");
        }
        if (!isActive(last)) {
          return demoError(
            409,
            "command_finished",
            "The sweep is already finished",
          );
        }
        last = { ...last, status: "cancelling", updated_at: iso(now()) };
        return demoJson(last);
      },
    },
  ];

  return {
    routes,
    seed: (sweep) => {
      last = sweep ? structuredClone(sweep) : null;
    },
    reset: () => {
      last = null;
      swept = false;
      counter = 0;
    },
  };
};
