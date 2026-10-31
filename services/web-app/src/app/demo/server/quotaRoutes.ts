import { demoError, demoJson, demoNoContent } from "@shared/api/demo";
import type { DemoResponse, DemoRoute } from "@shared/api/demo";
import {
  AdminAutoscalePolicySchema,
  AdminQuotaPolicySchema,
  SetAdminQuotaOverrideRequestSchema,
  type AdminAutoscalePolicy,
  type AdminAutoscaleStatus,
  type AdminQuotaOverride,
  type AdminQuotaPolicy,
  type MyUsage,
  type UsageLine,
} from "@entities/quota";
import type { ServerDemoWorld } from "./world";

// Демо квот по видам ресурсов, использования, ИИ-шлюза и автомасштабирования.
// Тела совпадают с contracts/server/fixtures (AdminQuotaPolicy, MyUsageResponse, AdminAutoscaleStatus...).

const GIB = 1024 ** 3;
const NOW = "2026-11-10T12:00:00Z";
const NEXT_MONTH = "2026-12-01T00:00:00Z";
const TOMORROW = "2026-11-11T00:00:00Z";

type QuotaDemo = {
  policy: AdminQuotaPolicy;
  overrides: AdminQuotaOverride[];
  autoscale: AdminAutoscalePolicy;
};

const states = new WeakMap<ServerDemoWorld, QuotaDemo>();

const stateOf = (world: ServerDemoWorld): QuotaDemo => {
  let state = states.get(world);
  if (!state) {
    state = {
      policy: {
        defaults: [
          { kind: "storage", user: 2 * GIB, org: 20 * GIB },
          { kind: "builds", user: 30, org: null },
          { kind: "ai_tokens_day", user: null, org: null },
          { kind: "ai_tokens_month", user: 200000, org: 2000000 },
          { kind: "members", user: 5, org: null },
        ],
        warn_percent: 80,
        on_exceed: "deprioritize",
      },
      overrides: [
        {
          owner_kind: "org",
          owner_id: "hse-fkn",
          owner_name: "Факультет компьютерных наук",
          resource: "storage.bytes_org",
          hard_limit: 50 * GIB,
        },
      ],
      autoscale: {
        mode: "off",
        min_runners: 1,
        max_runners: 6,
        target_queue_per_slot: 2,
        scale_up_wait_s: 30,
        cooldown_up_s: 60,
        cooldown_down_s: 300,
        idle_before_down_s: 300,
        step_up: 2,
        step_down: 1,
        webhook_url: null,
      },
    };
    states.set(world, state);
  }
  return state;
};

const line = (
  kind: UsageLine["kind"],
  scope: UsageLine["scope"],
  used: number,
  limit: number | null,
  warn: number,
): UsageLine => {
  const percent =
    limit === null ? null : Math.min(100, Math.floor((used * 100) / limit));
  const state: UsageLine["state"] =
    limit === null
      ? "unlimited"
      : used >= limit
        ? "exceeded"
        : used * 100 >= limit * warn
          ? "warning"
          : "ok";
  return {
    kind,
    scope,
    unit:
      kind === "storage"
        ? "bytes"
        : kind === "members"
          ? "members"
          : kind === "builds"
            ? "builds"
            : "tokens",
    used,
    limit,
    percent,
    state,
    source: limit === null ? null : "installation",
    resets_at:
      kind === "builds" || kind === "ai_tokens_month"
        ? NEXT_MONTH
        : kind === "ai_tokens_day"
          ? TOMORROW
          : null,
  };
};

const usageFor = (state: QuotaDemo): MyUsage => {
  const limit = (kind: string, scope: "user" | "org") =>
    state.policy.defaults.find((d) => d.kind === kind)?.[scope] ?? null;
  const warn = state.policy.warn_percent;
  return {
    user: {
      owner_id: "demo-user",
      owner_name: "Демо",
      lines: [
        line("storage", "user", 1.7 * GIB, limit("storage", "user"), warn),
        line("builds", "user", 27, limit("builds", "user"), warn),
        line(
          "ai_tokens_day",
          "user",
          1200,
          limit("ai_tokens_day", "user"),
          warn,
        ),
        line(
          "ai_tokens_month",
          "user",
          200000,
          limit("ai_tokens_month", "user"),
          warn,
        ),
        line("members", "user", 3, limit("members", "user"), warn),
      ],
    },
    orgs: [],
    warn_percent: warn,
  };
};

const autoscaleStatus = (state: QuotaDemo): AdminAutoscaleStatus => ({
  policy: state.autoscale,
  metrics: {
    queued: 9,
    oldest_wait_s: 42,
    running: 2,
    runners_online: 1,
    slots_total: 2,
    slots_busy: 2,
  },
  decision: {
    current: 1,
    desired: 3,
    action: "up",
    reason: "queue_depth",
    wait_s: 0,
  },
  last_outcome: null,
  last_up_at: null,
  last_down_at: null,
  orchestrator_current: null,
  evaluated_at: NOW,
  webhook_secret_set: false,
});

const invalid = () => demoError(422, "input_invalid", "Invalid input");

export const createQuotaAdminRoutes = (
  getWorld: () => ServerDemoWorld,
): DemoRoute[] => {
  const state = () => stateOf(getWorld());
  const guard = (): DemoResponse | null => {
    const { user } = getWorld().bootstrap;
    if (user === null)
      return demoError(401, "auth_required", "Authentication required");
    return user.is_instance_admin
      ? null
      : demoError(404, "not_found", "Not Found");
  };
  const guarded =
    (handler: DemoRoute["handler"]): DemoRoute["handler"] =>
    (req) =>
      guard() ?? handler(req);

  return [
    {
      method: "GET",
      pattern: "/quota-policy",
      handler: guarded(() => demoJson(state().policy)),
    },
    {
      method: "PUT",
      pattern: "/quota-policy",
      handler: guarded((req) => {
        const parsed = AdminQuotaPolicySchema.safeParse(req.body);
        if (!parsed.success) return invalid();
        state().policy = parsed.data;
        return demoJson(state().policy);
      }),
    },
    {
      method: "GET",
      pattern: "/quota-overrides",
      handler: guarded(() => demoJson(state().overrides)),
    },
    {
      method: "PUT",
      pattern: "/quota-overrides",
      handler: guarded((req) => {
        const parsed = SetAdminQuotaOverrideRequestSchema.safeParse(req.body);
        if (!parsed.success) return invalid();
        const next: AdminQuotaOverride = {
          ...parsed.data,
          owner_name: parsed.data.owner_id,
        };
        const rest = state().overrides.filter(
          (o) =>
            !(
              o.owner_kind === next.owner_kind &&
              o.owner_id === next.owner_id &&
              o.resource === next.resource
            ),
        );
        state().overrides = [...rest, next];
        return demoJson(next);
      }),
    },
    {
      method: "DELETE",
      pattern: "/quota-overrides",
      handler: guarded((req) => {
        const q = req.query ?? {};
        state().overrides = state().overrides.filter(
          (o) =>
            !(
              o.owner_kind === q.owner_kind &&
              o.owner_id === q.owner_id &&
              o.resource === q.resource
            ),
        );
        return demoNoContent();
      }),
    },
    {
      method: "GET",
      pattern: "/usage",
      handler: guarded(() =>
        demoJson({
          owner_id: "demo-user",
          owner_name: "Демо",
          lines: usageFor(state()).user.lines,
        }),
      ),
    },
    {
      method: "GET",
      pattern: "/usage/summary",
      handler: guarded(() =>
        demoJson({
          totals: {
            storage: 12 * GIB,
            builds: 412,
            ai_tokens_day: 9000,
            ai_tokens_month: 880000,
          },
          top_builds: [{ user_id: "demo-user", name: "Демо", used: 120 }],
          top_ai_tokens: [],
          period_start: "2026-11-01",
          on_exceed: state().policy.on_exceed,
        }),
      ),
    },
    {
      method: "POST",
      pattern: "/usage/reset",
      handler: guarded(() => demoNoContent()),
    },
    {
      method: "GET",
      pattern: "/ai-gateway",
      handler: guarded(() =>
        demoJson([
          {
            id: "0b9f2a0e-0000-4000-8000-000000000001",
            name: "OpenAI общий",
            type: "openai",
            breaker: "closed",
            failures: 0,
            calls_24h: 340,
            errors_24h: 2,
            denied_24h: 5,
            input_tokens_24h: 410000,
            output_tokens_24h: 96000,
          },
        ]),
      ),
    },
    {
      method: "GET",
      pattern: "/autoscale",
      handler: guarded(() => demoJson(autoscaleStatus(state()))),
    },
    {
      method: "PUT",
      pattern: "/autoscale",
      handler: guarded((req) => {
        const parsed = AdminAutoscalePolicySchema.safeParse(req.body);
        if (!parsed.success) return invalid();
        state().autoscale = parsed.data;
        return demoJson(autoscaleStatus(state()));
      }),
    },
  ];
};

export const createUsageRoutes = (
  getWorld: () => ServerDemoWorld,
): DemoRoute[] => [
  {
    method: "GET",
    pattern: "/usage",
    handler: () => {
      const { user } = getWorld().bootstrap;
      if (user === null)
        return demoError(401, "auth_required", "Authentication required");
      return demoJson(usageFor(stateOf(getWorld())));
    },
  },
];
