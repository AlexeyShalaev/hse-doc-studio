import { demoError, demoJson, demoNoContent } from "@shared/api/demo";
import type { DemoResponse, DemoRoute } from "@shared/api/demo";
import type {
  AdminJob,
  AdminRunner,
  AdminRunnerToken,
} from "@entities/session";
import {
  boolParam,
  cursorList,
  enumParam,
  invalidQuery,
  offsetList,
  queryAll,
  queryOne,
  timeParam,
} from "./demoList";
import {
  adminOpsOf,
  adminOrgsOf,
  adminPeopleOf,
  type ServerDemoWorld,
} from "./world";

// Демо админки: раннеры, токены регистрации, очередь, квоты, сервисы и место.
// Тела совпадают с contracts/server/fixtures (AdminRunnerList, AdminJobPage, AdminQuotas и т.д.).
// Мир хранит данные в виде экранов (с именами), а наружу отдаёт их в проводной форме сервера:
// строка очереди несёт имена человека, организации, проекта и раннера, как JOIN у настоящего API.
//
// Правила, как у настоящего API: только админ установки (остальным 404), секрет токена виден
// только в ответе на создание или ротацию, отозванный раннер исчезает из ротации.
//
// Особые значения: имя токена с limit в начале даёт 429 rate_limited; отмена завершённой
// задачи возвращает её без изменений; сервис с id storage при проверке в сценарии с падением остаётся down.
//
// Списки идут по единому контракту (demoList.ts): раннеры и токены страницами с
// фильтрами и сортировкой, очередь курсором.

const RUNNER_STATUSES = [
  "online",
  "stale",
  "offline",
  "paused",
  "revoked",
] as const;
const TOKEN_STATUSES = ["active", "expired", "exhausted", "revoked"] as const;
const JOB_STATES = [
  "queued",
  "running",
  "succeeded",
  "failed",
  "cancelled",
  "timed_out",
] as const;

/** Версии раннеров сравниваются по числам: 0.10.0 новее 0.9.9. */
const versionKey = (v: string): string =>
  v
    .split(".")
    .map((part) => part.replace(/\D/g, "").padStart(5, "0"))
    .join(".");

const tokenStatus = (t: AdminRunnerToken): (typeof TOKEN_STATUSES)[number] =>
  t.revoked
    ? "revoked"
    : t.uses >= t.max_uses
      ? "exhausted"
      : t.expires_at !== null && Date.parse(t.expires_at) <= Date.now()
        ? "expired"
        : "active";

// Порядковый номер задачи (seq): ключ курсора очереди. Считается по времени
// постановки, пересчитывается, когда меняется массив задач. Вместе с ним
// кэшируется порядок «новые первыми»: в большом мире 40 000 задач, и
// сортировать их на каждый запрос с фильтром долго.
type QueueOrder = { seq: Map<string, number>; newest: AdminJob[] };
const orderCache = new WeakMap<AdminJob[], QueueOrder>();
const orderOf = (jobs: AdminJob[]): QueueOrder => {
  const cached = orderCache.get(jobs);
  if (cached?.seq.size === jobs.length) return cached;
  const at = new Map(jobs.map((j) => [j.id, Date.parse(j.created_at)]));
  const ordered = [...jobs].sort(
    (a, b) =>
      (at.get(a.id) ?? 0) - (at.get(b.id) ?? 0) || (a.id < b.id ? -1 : 1),
  );
  const order = {
    seq: new Map(ordered.map((j, i) => [j.id, i + 1])),
    newest: ordered.reverse(),
  };
  orderCache.set(jobs, order);
  return order;
};

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

  /** Новейшая версия среди неотозванных раннеров: от неё считаются устаревшие. */
  const newestVersion = (): string | null =>
    state()
      .runners.filter((r) => !r.revoked)
      .map((r) => r.version)
      .sort((a, b) => (versionKey(a) < versionKey(b) ? 1 : -1))[0] ?? null;

  // Почта по человеку: справочник строится раз на массив людей, а не на строку.
  const emailCache = new WeakMap<object, Map<string, string>>();
  const emailOf = (id: string): string | null => {
    const users = adminPeopleOf(getWorld()).users;
    let map = emailCache.get(users);
    if (!map) {
      map = new Map(users.map((u) => [u.id, u.email]));
      emailCache.set(users, map);
    }
    return map.get(id) ?? null;
  };
  const runnerNameOf = (j: AdminJob): string | null =>
    j.runner_id === null
      ? null
      : (state().runners.find((r) => r.id === j.runner_id)?.name ??
        j.runner_name);

  const wireJob = (j: AdminJob) => ({
    id: j.id,
    kind: j.kind,
    state: j.status,
    project_id: j.project_id ?? "-",
    user_id: j.user_id,
    org_id: state().jobOrgs?.get(j.id)?.id ?? null,
    tags: j.tags,
    priority_class: j.priority,
    queued_at: j.created_at,
    started_at: j.started_at,
    finished_at: j.finished_at,
    attempt: j.attempt,
    max_attempts: j.max_attempts,
    runner_id: j.runner_id,
    cancel_requested: false,
    error_code: j.error,
    user_name: j.user_name || null,
    user_email: j.user_name ? emailOf(j.user_id) : null,
    org_name: state().jobOrgs?.get(j.id)?.name ?? null,
    project_name: j.project_name,
    runner_name: runnerNameOf(j),
  });

  const summary = () => {
    const jobs = state().jobs;
    const queued = jobs.filter((j) => j.status === "queued");
    // Ожидание считается и по тем, кто ещё в очереди: иначе 95-й процентиль
    // оказывается меньше ожиданий, видных в таблице.
    const waits = jobs.map((j) => j.wait_s).sort((a, b) => a - b);
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
      handler: guarded((req) => {
        const statuses = enumParam(req, "status", RUNNER_STATUSES);
        const outdated = boolParam(req, "outdated");
        if (statuses === null || outdated === "bad") return invalidQuery();
        const tags = queryAll(req, "tag");
        const classes = queryAll(req, "resource_class");
        const newest = newestVersion();
        const rank = (r: AdminRunner) => RUNNER_STATUSES.indexOf(r.status);
        const rows = state()
          .runners.map(wireRunner)
          .filter(
            (r) =>
              (statuses.length === 0 || statuses.includes(r.status)) &&
              (tags.length === 0 || tags.some((t) => r.tags.includes(t))) &&
              (classes.length === 0 || classes.includes(r.resource_class)) &&
              (outdated === null ||
                (!r.revoked &&
                  newest !== null &&
                  versionKey(r.version) < versionKey(newest)) === outdated),
          );
        return offsetList(req, rows, {
          sort: {
            name: (r: AdminRunner) => r.name,
            status: rank,
            last_seen_at: (r: AdminRunner) => r.last_seen_at,
            created_at: (r: AdminRunner) => r.created_at,
            version: (r: AdminRunner) => versionKey(r.version),
          },
          defaultSort: "status",
          search: (r) => [r.name, r.version, ...r.tags],
          id: (r) => r.id,
        });
      }),
    },
    {
      // Счётчики для KPI на «Раннерах» и в «Обзоре» без чтения списка.
      method: "GET",
      pattern: "/runners/summary",
      handler: guarded(() => {
        const rows = state().runners.map(wireRunner);
        const count = (st: AdminRunner["status"]) =>
          rows.filter((r) => r.status === st).length;
        const newest = newestVersion();
        return demoJson({
          online: count("online"),
          paused: count("paused"),
          stale: count("stale"),
          offline: count("offline"),
          revoked: count("revoked"),
          outdated: rows.filter(
            (r) =>
              !r.revoked &&
              newest !== null &&
              versionKey(r.version) < versionKey(newest),
          ).length,
          newest_version: newest,
        });
      }),
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
      handler: guarded((req) => {
        const statuses = enumParam(req, "status", TOKEN_STATUSES);
        if (statuses === null) return invalidQuery();
        return offsetList(
          req,
          state().tokens.filter(
            (t) => statuses.length === 0 || statuses.includes(tokenStatus(t)),
          ),
          {
            sort: {
              created_at: (t: AdminRunnerToken) => t.created_at,
              expires_at: (t: AdminRunnerToken) => t.expires_at,
              label: (t: AdminRunnerToken) => t.label,
            },
            defaultSort: "-created_at",
            search: (t) => [t.label],
            id: (t) => t.id,
          },
        );
      }),
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
        const states = enumParam(req, "state", JOB_STATES);
        const from = timeParam(req, "from");
        const to = timeParam(req, "to");
        if (states === null || from === "bad" || to === "bad") {
          return invalidQuery();
        }
        const kinds = queryAll(req, "kind");
        const user = queryOne(req, "user_id");
        const org = queryOne(req, "org_id");
        const project = queryOne(req, "project_id");
        const runner = queryOne(req, "runner_id");
        const jobs = state().jobs;
        const { seq, newest: ordered } = orderOf(jobs);
        const key = (j: AdminJob) => seq.get(j.id) ?? 0;
        const orgOf = state().jobOrgs;
        const filtered =
          states.length > 0 ||
          kinds.length > 0 ||
          [user, org, project, runner].some((v) => v !== null) ||
          from !== null ||
          to !== null;
        return cursorList(req, ordered, key, {
          accept: (j) => {
            const at = Date.parse(j.created_at);
            return (
              (states.length === 0 || states.includes(j.status)) &&
              (kinds.length === 0 || kinds.includes(j.kind)) &&
              (user === null || j.user_id === user) &&
              // Организацию дают и id, и адрес из пикера организаций.
              (org === null ||
                [org, `org_${org}`].includes(orgOf?.get(j.id)?.id ?? "")) &&
              (project === null || j.project_id === project) &&
              (runner === null || j.runner_id === runner) &&
              (from === null || at >= from) &&
              (to === null || at < to)
            );
          },
          view: wireJob,
          totalEstimate: filtered ? null : jobs.length,
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
    {
      // Все владельцы места: страницей, а сводка /storage держит пятерку для KPI.
      method: "GET",
      pattern: "/storage/owners",
      handler: guarded((req) => {
        const kinds = enumParam(req, "kind", ["user", "org"] as const);
        if (kinds === null) return invalidQuery();
        const world = getWorld();
        type Owner = {
          kind: "user" | "org";
          id: string;
          name: string;
          email: string | null;
          projects: number;
          bytes: number;
        };
        // Размер проекта в демо постоянный для владельца: от 20 до 180 МБ.
        const sizeOf = (id: string) => {
          let h = 0;
          for (const ch of id) h = (h * 31 + ch.charCodeAt(0)) >>> 0;
          return (20 + (h % 160)) * 1024 * 1024;
        };
        const rows: Owner[] = [
          ...adminPeopleOf(world)
            .users.filter((u) => u.project_count > 0)
            .map((u): Owner => ({
              kind: "user",
              id: u.id,
              name: u.name,
              email: u.email,
              projects: u.project_count,
              bytes: u.project_count * sizeOf(u.id),
            })),
          ...adminOrgsOf(world)
            .orgs.filter((o) => o.project_count > 0)
            .map((o): Owner => ({
              kind: "org",
              id: o.slug,
              name: o.name,
              email: null,
              projects: o.project_count,
              bytes: o.project_count * sizeOf(o.slug),
            })),
        ].filter((o) => kinds.length === 0 || kinds.includes(o.kind));
        return offsetList(req, rows, {
          sort: {
            projects: (o: Owner) => o.projects,
            bytes: (o: Owner) => o.bytes,
            name: (o: Owner) => o.name,
          },
          defaultSort: "-projects",
          search: (o) => [o.name, o.email],
          id: (o) => `${o.kind}:${o.id}`,
        });
      }),
    },
  ];
};
