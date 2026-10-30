import type {
  AdminJob,
  AdminQuotas,
  AdminRunner,
  AdminRunnerToken,
  AdminService,
  AdminStorage,
  JobState,
} from "@entities/session";
import type { ServerDemoOpsSeed } from "./scenarios";

// Операционные экраны в демо-мире админки: раннеры, токены, очередь, квоты, сервисы, место.
// Формы совпадают с contracts/server/fixtures. Время считается от момента создания мира,
// чтобы статусы по last_seen_at выглядели живыми.

export type DemoAdminOps = {
  runners: AdminRunner[];
  tokens: AdminRunnerToken[];
  jobs: AdminJob[];
  quotas: AdminQuotas;
  services: AdminService[];
  storage: AdminStorage;
  /** Сколько токенов и раннеров выдано: для новых идентификаторов. */
  counter: number;
  /** Организация задачи (большой мир): фильтр очереди по org_id и подпись. */
  jobOrgs?: Map<string, { id: string; name: string }>;
};

const ago = (seconds: number, now: number): string =>
  new Date(now - seconds * 1000).toISOString();
const ahead = (seconds: number, now: number): string =>
  new Date(now + seconds * 1000).toISOString();

const runner = (
  id: string,
  name: string,
  tags: string[],
  seenAgo: number | null,
  now: number,
  extra: Partial<AdminRunner> = {},
): AdminRunner => ({
  id,
  name,
  status: "offline",
  tags,
  concurrency: 2,
  resource_class: "standard",
  version: "0.3.0",
  created_at: ago(6 * 86400, now),
  last_seen_at: seenAgo === null ? null : ago(seenAgo, now),
  paused: false,
  revoked: false,
  ...extra,
});

const token = (
  id: string,
  label: string,
  now: number,
  extra: Partial<AdminRunnerToken> = {},
): AdminRunnerToken => ({
  id,
  label,
  created_at: ago(3600, now),
  expires_at: ahead(23 * 3600, now),
  max_uses: 1,
  uses: 0,
  revoked: false,
  ...extra,
});

type JobSeed = {
  id: string;
  kind: string;
  status: JobState;
  waited: number;
  age: number;
  user: [string, string];
  project: [string, string] | null;
  runner?: [string, string];
  attempt?: number;
  duration?: number;
  priority?: AdminJob["priority"];
  error?: string;
};

const TAGS: Record<string, string[]> = {
  compile: ["compile"],
  "office.convert": ["office"],
  "signature.verify_detached": ["verify"],
  "pack.submission": ["pack"],
};

const job = (seed: JobSeed, now: number): AdminJob => {
  const started = seed.status === "queued" ? null : seed.age - seed.waited;
  const finished =
    seed.status === "queued" || seed.status === "running"
      ? null
      : (started ?? 0) - (seed.duration ?? 20);
  return {
    id: seed.id,
    kind: seed.kind,
    status: seed.status,
    priority:
      seed.priority ?? (seed.kind === "compile" ? "interactive" : "checks"),
    project_id: seed.project?.[0] ?? null,
    project_name: seed.project?.[1] ?? null,
    user_id: seed.user[0],
    user_name: seed.user[1],
    tags: TAGS[seed.kind] ?? [],
    runner_id: seed.runner?.[0] ?? null,
    runner_name: seed.runner?.[1] ?? null,
    attempt: seed.attempt ?? (seed.status === "queued" ? 0 : 1),
    max_attempts: 3,
    created_at: ago(seed.age, now),
    started_at: started === null ? null : ago(started, now),
    finished_at: finished === null ? null : ago(Math.max(0, finished), now),
    wait_s: seed.waited,
    error: seed.error ?? null,
  };
};

// Люди те же, что в демо-мире пользователей: очередь находит их имена по идентификатору.
// Последний удалён из установки, его задачи остаются в истории без имени.
const IVAN: [string, string] = ["u_01hx7k1a0b", "Иван Сидоров"];
const MARIA: [string, string] = ["u_01hx7k2c1d", "Мария Келлер"];
const PETR: [string, string] = ["u_01hx7k3e2f", "Пётр Орлов"];
const DARYA: [string, string] = ["u_01hx7k6k5l", "Дарья Лис"];
const GONE: [string, string] = ["u_01hx7k9x8w", ""];
const BERTIE: [string, string] = ["p_01hxa1c4de", "Bertie: курсовая"];
const LAB: [string, string] = ["p_01hxa2f8gh", "Лаборатория: отчёт"];
const THESIS: [string, string] = ["p_01hxa3k2mn", "ВКР: глава 2"];
const R1: [string, string] = ["rn_01hxb1", "runner-1"];
const R2: [string, string] = ["rn_01hxb2", "runner-2"];

const jobsFor = (seed: ServerDemoOpsSeed, now: number): AdminJob[] => {
  if (seed === "fresh") return [];
  if (seed === "runners_offline") {
    const rows: JobSeed[] = [
      {
        id: "j_01hxe1",
        kind: "compile",
        status: "queued",
        waited: 1260,
        age: 1260,
        user: MARIA,
        project: BERTIE,
      },
      {
        id: "j_01hxe2",
        kind: "compile",
        status: "queued",
        waited: 980,
        age: 980,
        user: PETR,
        project: LAB,
      },
      {
        id: "j_01hxe3",
        kind: "office.convert",
        status: "queued",
        waited: 640,
        age: 640,
        user: DARYA,
        project: THESIS,
      },
      {
        id: "j_01hxe4",
        kind: "pack.submission",
        status: "queued",
        waited: 300,
        age: 300,
        user: IVAN,
        project: BERTIE,
        priority: "batch",
      },
      {
        id: "j_01hxe5",
        kind: "compile",
        status: "failed",
        waited: 20,
        age: 3300,
        user: MARIA,
        project: BERTIE,
        runner: R1,
        attempt: 3,
        duration: 90,
        error: "runner_lost",
      },
    ];
    return rows.map((r) => job(r, now));
  }
  const rows: JobSeed[] = [
    {
      id: "j_01hxd1",
      kind: "compile",
      status: "running",
      waited: 4,
      age: 38,
      user: MARIA,
      project: BERTIE,
      runner: R1,
    },
    {
      id: "j_01hxd2",
      kind: "compile",
      status: "running",
      waited: 7,
      age: 55,
      user: PETR,
      project: LAB,
      runner: R2,
    },
    {
      id: "j_01hxd3",
      kind: "office.convert",
      status: "running",
      waited: 2,
      age: 25,
      user: DARYA,
      project: THESIS,
      runner: R1,
    },
    {
      id: "j_01hxd4",
      kind: "compile",
      status: "queued",
      waited: 21,
      age: 21,
      user: IVAN,
      project: BERTIE,
    },
    {
      id: "j_01hxd5",
      kind: "compile",
      status: "queued",
      waited: 14,
      age: 14,
      user: DARYA,
      project: LAB,
    },
    {
      id: "j_01hxd6",
      kind: "pack.submission",
      status: "queued",
      waited: 9,
      age: 9,
      user: PETR,
      project: LAB,
      priority: "batch",
    },
    {
      id: "j_01hxd7",
      kind: "signature.verify_detached",
      status: "queued",
      waited: 3,
      age: 3,
      user: MARIA,
      project: THESIS,
    },
    {
      id: "j_01hxd8",
      kind: "compile",
      status: "succeeded",
      waited: 3,
      age: 400,
      user: MARIA,
      project: BERTIE,
      runner: R1,
      duration: 41,
    },
    {
      id: "j_01hxd9",
      kind: "compile",
      status: "failed",
      waited: 5,
      age: 620,
      user: PETR,
      project: LAB,
      runner: R2,
      duration: 18,
      error: "artifact_invalid",
    },
    {
      id: "j_01hxda",
      kind: "pack.submission",
      status: "succeeded",
      waited: 6,
      age: 900,
      user: DARYA,
      project: THESIS,
      runner: R1,
      duration: 33,
      priority: "batch",
    },
    {
      id: "j_01hxdb",
      kind: "office.convert",
      status: "timed_out",
      waited: 8,
      age: 1500,
      user: GONE,
      project: BERTIE,
      runner: R2,
      attempt: 2,
      duration: 180,
      error: "job_timeout",
    },
    {
      id: "j_01hxdc",
      kind: "compile",
      status: "cancelled",
      waited: 2,
      age: 2100,
      user: IVAN,
      project: BERTIE,
      duration: 4,
    },
    {
      id: "j_01hxdd",
      kind: "signature.verify_detached",
      status: "succeeded",
      waited: 1,
      age: 2600,
      user: PETR,
      project: LAB,
      runner: R1,
      duration: 3,
    },
  ];
  return rows.map((r) => job(r, now));
};

const runnersFor = (seed: ServerDemoOpsSeed, now: number): AdminRunner[] => {
  if (seed === "fresh") return [];
  if (seed === "runners_offline") {
    return [
      runner("rn_01hxb1", "runner-1", ["compile", "office"], 5400, now),
      runner("rn_01hxb2", "runner-2", ["compile", "verify", "pack"], 9000, now),
      runner("rn_01hxb3", "runner-3", ["compile"], null, now),
    ];
  }
  return [
    runner("rn_01hxb1", "runner-1", ["compile", "office"], 6, now),
    runner("rn_01hxb2", "runner-2", ["compile", "verify", "pack"], 22, now, {
      concurrency: 4,
    }),
    runner("rn_01hxb3", "runner-3", ["compile"], 140, now, {
      version: "0.2.4",
    }),
    runner("rn_01hxb4", "runner-4", ["office"], 30, now, { paused: true }),
    runner("rn_01hxb5", "runner-5", ["compile"], 7200, now),
    runner("rn_01hxb6", "runner-6", ["verify"], 86400, now, { revoked: true }),
  ];
};

const tokensFor = (seed: ServerDemoOpsSeed, now: number): AdminRunnerToken[] =>
  seed === "fresh"
    ? []
    : [
        token("rt_01hxc1", "Сервер в аудитории 305", now),
        token("rt_01hxc2", "Запасной", now, { max_uses: 5, uses: 2 }),
        token("rt_01hxc3", "Тестовый стенд", now, {
          created_at: ago(2 * 86400, now),
          expires_at: ago(3600, now),
        }),
        token("rt_01hxc4", "Отозванный", now, { uses: 1, revoked: true }),
      ];

const GIB = 1024 ** 3;

const servicesFor = (seed: ServerDemoOpsSeed): AdminService[] => {
  const svc = (
    id: string,
    kind: AdminService["kind"],
    status: AdminService["status"],
    detail: string | null,
    counts: [number, number] | null = null,
  ): AdminService => ({
    id,
    kind,
    status,
    detail,
    online: counts?.[0] ?? null,
    total: counts?.[1] ?? null,
  });
  if (seed === "fresh") {
    return [
      svc("database", "database", "ok", null),
      svc("s3", "storage", "unconfigured", null),
      svc("languagetool", "languagetool", "unconfigured", null),
      svc("onlyoffice", "onlyoffice", "unconfigured", null),
      svc("runners", "runners", "unconfigured", null, [0, 0]),
      svc("smtp", "smtp", "unconfigured", null),
    ];
  }
  if (seed === "services_degraded") {
    return [
      svc("database", "database", "ok", null),
      svc("s3", "storage", "down", "timeout"),
      svc("languagetool", "languagetool", "down", "no_healthy_replica"),
      svc("onlyoffice", "onlyoffice", "down", "no_healthy_replica"),
      svc("runners", "runners", "ok", null, [2, 5]),
      svc("smtp", "smtp", "unconfigured", null),
    ];
  }
  const runnersDown = seed === "runners_offline";
  return [
    svc("database", "database", "ok", null),
    svc("s3", "storage", "ok", null),
    svc("languagetool", "languagetool", "ok", null),
    svc("onlyoffice", "onlyoffice", "ok", null),
    runnersDown
      ? svc("runners", "runners", "down", "no_online_runner", [0, 3])
      : svc("runners", "runners", "ok", null, [2, 5]),
    svc("smtp", "smtp", "ok", null),
  ];
};

const g = (n: number): number => Math.round(n * GIB);

const storageFor = (seed: ServerDemoOpsSeed, now: number): AdminStorage => {
  if (seed === "fresh") {
    return {
      blob_count: 0,
      blob_bytes: 0,
      projects: 0,
      deleted_projects: 0,
      // Проектов ещё нет: занято только то, что поставили с сервером.
      free_bytes: g(196.6),
      volume_total_bytes: g(200),
      computed_at: ago(40, now),
      owners: [],
    };
  }
  return {
    blob_count: 1840,
    blob_bytes: g(2.1),
    projects: 38,
    deleted_projects: 3,
    free_bytes: seed === "services_degraded" ? g(2.4) : g(86),
    volume_total_bytes: seed === "services_degraded" ? g(40) : g(200),
    computed_at: ago(40, now),
    // Владельцы — люди с личными проектами (как у сервера), по убыванию числа проектов.
    owners: [
      { id: MARIA[0], name: MARIA[1], projects: 12 },
      { id: IVAN[0], name: IVAN[1], projects: 9 },
      { id: PETR[0], name: PETR[1], projects: 6 },
      { id: "u_01hx7k7m6n", name: "Екатерина Смирнова", projects: 4 },
      { id: DARYA[0], name: DARYA[1], projects: 3 },
      { id: "u_01hx7k8p7q", name: "Алексей Новиков", projects: 2 },
    ],
  };
};

export const createDemoAdminOps = (
  seed: ServerDemoOpsSeed = "default",
  now: number = Date.now(),
): DemoAdminOps => ({
  runners: runnersFor(seed, now),
  tokens: tokensFor(seed, now),
  jobs: jobsFor(seed, now),
  quotas: {
    user_concurrent: 2,
    org_concurrent: seed === "fresh" ? null : 6,
    max_duration_s: 600,
  },
  services: servicesFor(seed),
  storage: storageFor(seed, now),
  counter: 10,
});
