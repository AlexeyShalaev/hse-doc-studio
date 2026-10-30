import {
  demoError,
  demoJson,
  demoNoContent,
  queryString,
} from "@shared/api/demo";
import type { DemoResponse, DemoRoute } from "@shared/api/demo";
import type {
  AdminJob,
  AdminQueueSummary,
  AdminQuotas,
  AdminRunner,
  AdminRunnerToken,
} from "@entities/session";
import { adminOpsOf, adminOrgsOf, type ServerDemoWorld } from "./world";

// Демо админки: раннеры, токены регистрации, очередь, квоты, сервисы и место.
// Тела совпадают с contracts/server/fixtures (AdminRunner, AdminJobPage, AdminQuotas и т.д.).
//
// Правила, как у настоящего API: только админ установки (остальным 404), секрет токена виден
// только в ответе на создание или ротацию, отозванный раннер исчезает из ротации.
//
// Особые значения: имя токена с limit в начале даёт 429 rate_limited; отмена завершённой
// задачи даёт 409 job_finished; сервис с id storage при проверке в сценарии с падением остаётся down.

const str = (value: unknown): string =>
  typeof value === "string" ? value : "";
const num = (value: unknown): number | null =>
  typeof value === "number" && Number.isInteger(value) ? value : null;

const notFound = () => demoError(404, "not_found", "Not Found");
const invalid = () => demoError(422, "input_invalid", "Invalid input");
const API_URL = "https://studio.example.org";

const ACTIVE: readonly AdminJob["status"][] = ["running", "queued"];
const RANK: Record<AdminJob["status"], number> = {
  queued: 0,
  running: 1,
  failed: 2,
  timed_out: 2,
  cancelled: 3,
  succeeded: 3,
};

const secret = (prefix: string): string =>
  `${prefix}_${Math.random().toString(36).slice(2, 12)}${Math.random()
    .toString(36)
    .slice(2, 10)}`;

const commandFor = (value: string): string =>
  `HSE_RUNNER__API_URL=${API_URL} HSE_RUNNER__TOKEN=${value} hse-doc-studio runner`;

export const createOpsRoutes = (
  getWorld: () => ServerDemoWorld,
): DemoRoute[] => {
  const state = () => adminOpsOf(getWorld());

  const guard = (): DemoResponse | null => {
    const { user } = getWorld().bootstrap;
    if (user === null)
      return demoError(401, "auth_required", "Authentication required");
    return user.is_instance_admin ? null : notFound();
  };
  const guarded =
    (handler: DemoRoute["handler"]): DemoRoute["handler"] =>
    (req) =>
      guard() ?? handler(req);

  const body = (req: { body?: unknown }): Record<string, unknown> =>
    (req.body ?? {}) as Record<string, unknown>;

  const runnerOf = (id: string | undefined): AdminRunner | undefined =>
    state().runners.find((r) => r.id === id && !r.revoked);

  const summary = (): AdminQueueSummary => {
    const jobs = state().jobs;
    const queued = jobs.filter((j) => j.status === "queued");
    const running = jobs.filter((j) => j.status === "running");
    const waits = jobs
      .filter((j) => j.status !== "queued")
      .map((j) => j.wait_s)
      .sort((a, b) => a - b);
    const at = (p: number): number | null =>
      waits.length === 0
        ? null
        : (waits[Math.min(waits.length - 1, Math.floor(waits.length * p))] ??
          null);
    const tags = [...new Set(jobs.flatMap((j) => j.tags))].sort();
    return {
      queued: queued.length,
      running: running.length,
      oldest_queued_age_s:
        queued.length === 0 ? null : Math.max(...queued.map((j) => j.wait_s)),
      wait_p50_s: at(0.5),
      wait_p95_s: at(0.95),
      tags: tags
        .map((tag) => {
          const mine = jobs.filter((j) => j.tags.includes(tag));
          const waited = mine.filter((j) => j.status !== "queued");
          return {
            tag,
            queued: mine.filter((j) => j.status === "queued").length,
            running: mine.filter((j) => j.status === "running").length,
            avg_wait_s:
              waited.length === 0
                ? null
                : Math.round(
                    waited.reduce((sum, j) => sum + j.wait_s, 0) /
                      waited.length,
                  ),
          };
        })
        .filter((t) => t.queued + t.running > 0),
    };
  };

  const setQuota = (
    slug: string,
    b: Record<string, unknown>,
  ): DemoResponse | AdminQuotas => {
    const concurrent =
      b.jobs_concurrent == null ? null : num(b.jobs_concurrent);
    const duration =
      b.jobs_max_duration_s == null ? null : num(b.jobs_max_duration_s);
    if (
      (b.jobs_concurrent != null &&
        (concurrent === null || concurrent < 1 || concurrent > 64)) ||
      (b.jobs_max_duration_s != null &&
        (duration === null || duration < 30 || duration > 86400))
    ) {
      return invalid();
    }
    const org = adminOrgsOf(getWorld()).orgs.find((o) => o.slug === slug);
    if (!org) return notFound();
    const quotas = state().quotas;
    const rest = quotas.overrides.filter((o) => o.org_slug !== slug);
    const next =
      concurrent === null && duration === null
        ? rest
        : [
            ...rest,
            {
              org_slug: slug,
              org_name: org.name,
              jobs_concurrent: concurrent,
              jobs_max_duration_s: duration,
            },
          ];
    state().quotas = { ...quotas, overrides: next };
    return state().quotas;
  };

  return [
    {
      method: "GET",
      pattern: "/runners",
      handler: guarded(() => demoJson(state().runners)),
    },
    {
      method: "PATCH",
      pattern: "/runners/:id",
      handler: guarded((req) => {
        const found = runnerOf(req.params.id);
        if (!found) return notFound();
        const paused = body(req).paused;
        if (typeof paused !== "boolean") return invalid();
        found.paused = paused;
        return demoNoContent();
      }),
    },
    {
      method: "POST",
      pattern: "/runners/:id/rotate-token",
      handler: guarded((req) => {
        const found = runnerOf(req.params.id);
        if (!found) return notFound();
        const value = secret("hse_rn");
        return demoJson({
          runner: found,
          runner_token: value,
          command: commandFor(value),
        });
      }),
    },
    {
      method: "DELETE",
      pattern: "/runners/:id",
      handler: guarded((req) => {
        const found = runnerOf(req.params.id);
        if (!found) return notFound();
        found.revoked = true;
        return demoNoContent();
      }),
    },

    {
      method: "GET",
      pattern: "/runner-tokens",
      handler: guarded(() => demoJson(state().tokens)),
    },
    {
      method: "POST",
      pattern: "/runner-tokens",
      handler: guarded((req) => {
        const b = body(req);
        const label = str(b.label).trim();
        const ttl = num(b.ttl_hours);
        const uses = num(b.max_uses);
        if (
          label.length > 128 ||
          ttl === null ||
          ttl < 1 ||
          ttl > 720 ||
          uses === null ||
          uses < 1 ||
          uses > 100
        ) {
          return invalid();
        }
        if (label.toLowerCase().startsWith("limit")) {
          return demoError(429, "rate_limited", "Too many requests");
        }
        const ops = state();
        ops.counter += 1;
        const token: AdminRunnerToken = {
          id: `rt_demo${String(ops.counter)}`,
          label,
          created_at: new Date().toISOString(),
          expires_at: new Date(Date.now() + ttl * 3600_000).toISOString(),
          max_uses: uses,
          uses: 0,
          revoked: false,
        };
        ops.tokens = [token, ...ops.tokens];
        const value = secret("hse_rt");
        return demoJson(
          { token, secret: value, command: commandFor(value) },
          201,
        );
      }),
    },
    {
      method: "DELETE",
      pattern: "/runner-tokens/:id",
      handler: guarded((req) => {
        const found = state().tokens.find((t) => t.id === req.params.id);
        if (!found) return notFound();
        found.revoked = true;
        return demoNoContent();
      }),
    },

    {
      method: "GET",
      pattern: "/queue",
      handler: guarded((req) => {
        const status = queryString(req, "status");
        const kind = queryString(req, "kind");
        const q = (queryString(req, "q") ?? "").trim().toLowerCase();
        const limit = Math.max(
          1,
          Math.min(200, Number(queryString(req, "limit") ?? "25") || 25),
        );
        const rows = state()
          .jobs.filter(
            (j) =>
              (!status || j.status === status) &&
              (!kind || j.kind === kind) &&
              (q === "" ||
                j.user_name.toLowerCase().includes(q) ||
                (j.project_name ?? "").toLowerCase().includes(q)),
          )
          .sort(
            (a, b) =>
              RANK[a.status] - RANK[b.status] ||
              Date.parse(b.created_at) - Date.parse(a.created_at),
          );
        return demoJson({ items: rows.slice(0, limit), total: rows.length });
      }),
    },
    {
      method: "GET",
      pattern: "/queue/summary",
      handler: guarded(() => demoJson(summary())),
    },
    {
      method: "POST",
      pattern: "/jobs/:id/cancel",
      handler: guarded((req) => {
        const found = state().jobs.find((j) => j.id === req.params.id);
        if (!found) return notFound();
        if (!ACTIVE.includes(found.status)) {
          return demoError(409, "job_finished", "The job has finished");
        }
        found.status = "cancelled";
        found.finished_at = new Date().toISOString();
        return demoJson(found);
      }),
    },

    {
      method: "GET",
      pattern: "/quotas",
      handler: guarded(() => demoJson(state().quotas)),
    },
    {
      method: "PUT",
      pattern: "/quotas",
      handler: guarded((req) => {
        const b = body(req);
        const q = state().quotas;
        const concurrent =
          b.jobs_concurrent == null ? null : num(b.jobs_concurrent);
        const duration =
          b.jobs_max_duration_s == null ? null : num(b.jobs_max_duration_s);
        if (
          (b.jobs_concurrent != null &&
            (concurrent === null || concurrent < 1 || concurrent > 64)) ||
          (b.jobs_max_duration_s != null &&
            (duration === null || duration < 30 || duration > 86400))
        ) {
          return invalid();
        }
        if (
          (concurrent !== null && q.fields.jobs_concurrent?.locked) ||
          (duration !== null && q.fields.jobs_max_duration_s?.locked)
        ) {
          return demoError(409, "setting_locked", "Set by the environment");
        }
        state().quotas = {
          ...q,
          jobs_concurrent: concurrent ?? q.jobs_concurrent,
          jobs_max_duration_s: duration ?? q.jobs_max_duration_s,
          fields: {
            ...q.fields,
            ...(concurrent !== null
              ? { jobs_concurrent: { source: "admin", locked: false } }
              : {}),
            ...(duration !== null
              ? { jobs_max_duration_s: { source: "admin", locked: false } }
              : {}),
          },
        };
        return demoJson(state().quotas);
      }),
    },
    {
      method: "PUT",
      pattern: "/quotas/orgs/:slug",
      handler: guarded((req) => {
        const result = setQuota(req.params.slug ?? "", body(req));
        return "status" in result ? result : demoJson(result);
      }),
    },
    {
      method: "DELETE",
      pattern: "/quotas/orgs/:slug",
      handler: guarded((req) => {
        const q = state().quotas;
        if (!q.overrides.some((o) => o.org_slug === req.params.slug)) {
          return notFound();
        }
        state().quotas = {
          ...q,
          overrides: q.overrides.filter((o) => o.org_slug !== req.params.slug),
        };
        return demoJson(state().quotas);
      }),
    },

    {
      method: "GET",
      pattern: "/services",
      handler: guarded(() => demoJson(state().services)),
    },
    {
      method: "POST",
      pattern: "/services/:id/check",
      handler: guarded((req) => {
        const ops = state();
        const index = ops.services.findIndex((s) => s.id === req.params.id);
        const found = ops.services[index];
        if (!found) return notFound();
        const checked = { ...found, checked_at: new Date().toISOString() };
        ops.services = ops.services.map((s, i) => (i === index ? checked : s));
        return demoJson(checked);
      }),
    },
    {
      method: "GET",
      pattern: "/storage",
      handler: guarded(() => demoJson(state().storage)),
    },
  ];
};
