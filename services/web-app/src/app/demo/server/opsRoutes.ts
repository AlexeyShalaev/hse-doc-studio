import {
  demoError,
  demoJson,
  demoNoContent,
  queryString,
} from "@shared/api/demo";
import type { DemoResponse, DemoRoute } from "@shared/api/demo";
import type {
  AdminJob,
  AdminRunner,
  AdminRunnerToken,
} from "@entities/session";
import { adminOpsOf, type ServerDemoWorld } from "./world";

// Демо админки: раннеры, токены регистрации, очередь, квоты, сервисы и место.
// Тела совпадают с contracts/server/fixtures (AdminRunnerList, AdminJobPage, AdminQuotas и т.д.).
// Мир хранит данные в виде экранов (с именами), а наружу отдаёт их в проводной форме сервера:
// идентификаторы в ней заменены именами, чтобы демо читалось так же, как с настоящими данными.
//
// Правила, как у настоящего API: только админ установки (остальным 404), секрет токена виден
// только в ответе на создание или ротацию, отозванный раннер исчезает из ротации.
//
// Особые значения: имя токена с limit в начале даёт 429 rate_limited; отмена завершённой
// задачи возвращает её без изменений; сервис с id storage при проверке в сценарии с падением остаётся down.

const str = (value: unknown): string =>
  typeof value === "string" ? value : "";
const num = (value: unknown): number | null =>
  typeof value === "number" && Number.isInteger(value) ? value : null;

const notFound = () => demoError(404, "not_found", "Not Found");
const invalid = () => demoError(422, "input_invalid", "Invalid input");
// Те же пороги, что у сервера: в сети до минуты тишины, «затих» до пяти.
const runnerStatusOf = (r: AdminRunner): AdminRunner["status"] => {
  if (r.revoked) return "revoked";
  if (r.paused) return "paused";
  if (r.last_seen_at === null) return "offline";
  const age = (Date.now() - Date.parse(r.last_seen_at)) / 1000;
  return age <= 60 ? "online" : age <= 300 ? "stale" : "offline";
};
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

  const wireRunner = (r: AdminRunner): AdminRunner => ({
    ...r,
    status: runnerStatusOf(r),
  });

  const wireJob = (j: AdminJob) => ({
    id: j.id,
    kind: j.kind,
    state: j.status,
    project_id: j.project_name ?? "-",
    user_id: j.user_name,
    org_id: null,
    tags: j.tags,
    priority_class: j.priority,
    queued_at: j.created_at,
    started_at: j.started_at,
    finished_at: j.finished_at,
    attempt: j.attempt,
    max_attempts: j.max_attempts,
    runner_id: j.runner_name,
    cancel_requested: false,
    error_code: j.error,
  });

  const summary = () => {
    const jobs = state().jobs;
    const queued = jobs.filter((j) => j.status === "queued");
    const waits = jobs
      .filter((j) => j.status !== "queued")
      .map((j) => j.wait_s)
      .sort((a, b) => a - b);
    const at = (p: number): number | null =>
      waits.length === 0
        ? null
        : (waits[Math.min(waits.length - 1, Math.floor(waits.length * p))] ??
          null);
    const count = (status: AdminJob["status"]) =>
      jobs.filter((j) => j.status === status).length;
    const oldest = queued.length
      ? queued.reduce((a, b) =>
          Date.parse(a.created_at) <= Date.parse(b.created_at) ? a : b,
        )
      : null;
    const byClass: Record<string, number> = {};
    for (const j of queued)
      byClass[j.priority] = (byClass[j.priority] ?? 0) + 1;
    return {
      by_state: {
        queued: count("queued"),
        running: count("running"),
        succeeded: count("succeeded"),
        failed: count("failed"),
        cancelled: count("cancelled"),
        timed_out: count("timed_out"),
      },
      queued_by_class: byClass,
      oldest_queued_at: oldest?.created_at ?? null,
      wait_p50_s: at(0.5),
      wait_p95_s: at(0.95),
    };
  };

  const quotaValue = (
    value: unknown,
    min: number,
    max: number,
  ): number | null | "bad" => {
    if (value === null) return null;
    const n = num(value);
    return n === null || n < min || n > max ? "bad" : n;
  };

  return [
    {
      method: "GET",
      pattern: "/runners",
      handler: guarded(() => demoJson(state().runners.map(wireRunner))),
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
          runner: wireRunner(found),
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
        const status = queryString(req, "state");
        const kind = queryString(req, "kind");
        const limit = Math.max(
          1,
          Math.min(200, Number(queryString(req, "limit") ?? "25") || 25),
        );
        const rows = state()
          .jobs.filter(
            (j) =>
              (!status || j.status === status) && (!kind || j.kind === kind),
          )
          .sort(
            (a, b) =>
              RANK[a.status] - RANK[b.status] ||
              Date.parse(b.created_at) - Date.parse(a.created_at),
          );
        return demoJson({
          items: rows.slice(0, limit).map(wireJob),
          next_cursor: rows.length > limit ? String(limit) : null,
        });
      }),
    },
    {
      method: "GET",
      pattern: "/queue/summary",
      handler: guarded(() => demoJson(summary())),
    },
    {
      method: "POST",
      pattern: "/queue/:id/cancel",
      handler: guarded((req) => {
        const found = state().jobs.find((j) => j.id === req.params.id);
        if (!found) return notFound();
        // Как у сервера: завершённая задача остаётся как есть, отмена идемпотентна.
        if (!ACTIVE.includes(found.status)) return demoJson(wireJob(found));
        found.status = "cancelled";
        found.finished_at = new Date().toISOString();
        return demoJson(wireJob(found));
      }),
    },

    {
      method: "GET",
      pattern: "/quotas",
      handler: guarded(() =>
        demoJson({ ...state().quotas, on_exhausted: "wait" }),
      ),
    },
    {
      method: "PUT",
      pattern: "/quotas",
      handler: guarded((req) => {
        const b = body(req);
        const user = quotaValue(b.user_concurrent, 1, 1000);
        const org = quotaValue(b.org_concurrent, 1, 1000);
        const duration = quotaValue(b.max_duration_s, 10, 86400);
        if (user === "bad" || org === "bad" || duration === "bad") {
          return invalid();
        }
        state().quotas = {
          user_concurrent: user,
          org_concurrent: org,
          max_duration_s: duration,
        };
        return demoJson({ ...state().quotas, on_exhausted: "wait" });
      }),
    },

    {
      method: "GET",
      pattern: "/services",
      handler: guarded(() =>
        demoJson(
          state().services.map((x) => ({
            id: x.id,
            state: x.status === "unconfigured" ? "not_configured" : x.status,
            reason: x.detail,
            total: x.total,
            online: x.online,
          })),
        ),
      ),
    },
    {
      method: "GET",
      pattern: "/storage",
      handler: guarded(() => {
        const x = state().storage;
        return demoJson({
          blob_count: x.blob_count,
          blob_bytes: x.blob_bytes,
          projects: x.projects,
          deleted_projects: x.deleted_projects,
          top_owners: x.owners.map((o) => ({
            owner_id: o.id,
            owner_name: o.name,
            projects: o.projects,
          })),
          volume_total_bytes: x.volume_total_bytes,
          volume_free_bytes: x.free_bytes,
          computed_at: x.computed_at,
        });
      }),
    },
  ];
};
