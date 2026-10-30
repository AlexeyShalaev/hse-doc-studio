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

const ANNA: [string, string] = ["u_01hx7k2m9c", "Анна Петрова"];
const PETR: [string, string] = ["u_01hx7k4p6g", "Пётр Орлов"];
const OLGA: [string, string] = ["u_01hx7k5q7h", "Ольга Белова"];
const BERTIE: [string, string] = ["p_01hxa1c4de", "Bertie: курсовая"];
const LAB: [string, string] = ["p_01hxa2f8gh", "Лаборатория: отчёт"];
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
        user: ANNA,
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
        user: OLGA,
        project: BERTIE,
      },
      {
        id: "j_01hxe4",
        kind: "pack.submission",
        status: "queued",
        waited: 300,
        age: 300,
        user: ANNA,
        project: BERTIE,
        priority: "batch",
      },
      {
        id: "j_01hxe5",
        kind: "compile",
        status: "failed",
        waited: 20,
        age: 3300,
        user: ANNA,
        project: BERTIE,
        runner: R1,
        attempt: 3,
        duration: 90,
        error: "Раннер потерян: нет сигнала жизни",
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
      user: ANNA,
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
      user: OLGA,
      project: BERTIE,
      runner: R1,
    },
    {
      id: "j_01hxd4",
      kind: "compile",
      status: "queued",
      waited: 21,
      age: 21,
      user: ANNA,
      project: BERTIE,
    },
    {
      id: "j_01hxd5",
      kind: "compile",
      status: "queued",
      waited: 14,
      age: 14,
      user: OLGA,
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
      user: ANNA,
      project: BERTIE,
    },
    {
      id: "j_01hxd8",
      kind: "compile",
      status: "succeeded",
      waited: 3,
      age: 400,
      user: ANNA,
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
      error: "Сборка завершилась с ошибкой LaTeX: undefined control sequence",
    },
    {
      id: "j_01hxda",
      kind: "pack.submission",
      status: "succeeded",
      waited: 6,
      age: 900,
      user: OLGA,
      project: BERTIE,
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
      user: OLGA,
      project: BERTIE,
      runner: R2,
      attempt: 2,
      duration: 180,
      error: "Превышено время выполнения: 180 с",
    },
    {
      id: "j_01hxdc",
      kind: "compile",
      status: "cancelled",
      waited: 2,
      age: 2100,
      user: ANNA,
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

const servicesFor = (seed: ServerDemoOpsSeed, now: number): AdminService[] => {
  const at = ago(20, now);
  const svc = (
    id: string,
    kind: AdminService["kind"],
    status: AdminService["status"],
    latency: number | null,
    detail: string | null,
    replicas: AdminService["replicas"] = [],
  ): AdminService => ({
    id,
    kind,
    status,
    latency_ms: latency,
    detail,
    checked_at: at,
    replicas,
  });
  const rep = (
    name: string,
    status: AdminService["status"],
    latency: number | null,
    used: number | null,
    total: number | null,
  ): AdminService["replicas"][number] => ({
    name,
    status,
    latency_ms: latency,
    slots_used: used,
    slots_total: total,
  });
  if (seed === "fresh") {
    return [
      svc("database", "database", "ok", 3, null),
      svc("storage", "storage", "unconfigured", null, null),
      svc("languagetool", "languagetool", "unconfigured", null, null),
      svc("onlyoffice", "onlyoffice", "unconfigured", null, null),
      svc("runners", "runners", "down", null, "Нет ни одного раннера"),
      svc("smtp", "smtp", "unconfigured", null, null),
    ];
  }
  if (seed === "services_degraded") {
    return [
      svc("database", "database", "ok", 4, null),
      svc("storage", "storage", "down", null, "Хранилище не отвечает"),
      svc(
        "languagetool",
        "languagetool",
        "degraded",
        920,
        "Одна реплика не отвечает",
        [rep("lt-1", "ok", 340, 3, 4), rep("lt-2", "down", null, null, null)],
      ),
      svc("onlyoffice", "onlyoffice", "down", null, "Все реплики недоступны", [
        rep("oo-1", "down", null, null, null),
        rep("oo-2", "down", null, null, null),
      ]),
      svc("runners", "runners", "ok", null, null),
      svc("smtp", "smtp", "degraded", 2400, "Сервер почты отвечает медленно"),
    ];
  }
  const online = seed === "runners_offline" ? "down" : "ok";
  return [
    svc("database", "database", "ok", 3, null),
    svc("storage", "storage", "ok", 24, null),
    svc("languagetool", "languagetool", "ok", 110, null, [
      rep("lt-1", "ok", 105, 1, 4),
      rep("lt-2", "ok", 118, 0, 4),
    ]),
    svc("onlyoffice", "onlyoffice", "ok", 64, null, [
      rep("oo-1", "ok", 61, 3, 5),
      rep("oo-2", "ok", 67, 2, 5),
    ]),
    svc(
      "runners",
      "runners",
      online,
      null,
      online === "down" ? "Ни один раннер не в сети" : null,
    ),
    svc("smtp", "smtp", "ok", 180, null),
  ];
};

const g = (n: number): number => Math.round(n * GIB);

const storageFor = (seed: ServerDemoOpsSeed, now: number): AdminStorage => {
  if (seed === "fresh") {
    return {
      total_bytes: 0,
      free_bytes: g(120),
      volume_bytes: 0,
      object_bytes: 0,
      computed_at: ago(40, now),
      owners: [],
    };
  }
  return {
    total_bytes: g(5.2),
    free_bytes: seed === "services_degraded" ? g(2.4) : g(86),
    volume_bytes: g(3.1),
    object_bytes: g(2.1),
    computed_at: ago(40, now),
    owners: [
      {
        kind: "org",
        id: "msp-2025",
        name: "МСПИН 2025",
        bytes: g(3.6),
        projects: 31,
      },
      {
        kind: "user",
        id: "u_01hx7k2m9c",
        name: "Анна Петрова",
        bytes: g(0.8),
        projects: 2,
      },
      {
        kind: "org",
        id: "ai-lab",
        name: "Лаборатория ИИ",
        bytes: g(0.5),
        projects: 4,
      },
      {
        kind: "user",
        id: "u_01hx7k4p6g",
        name: "Пётр Орлов",
        bytes: g(0.3),
        projects: 1,
      },
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
    jobs_concurrent: 2,
    jobs_max_duration_s: 600,
    fields: {
      jobs_concurrent: { source: "default", locked: false },
      jobs_max_duration_s: { source: "default", locked: false },
    },
    overrides:
      seed === "fresh"
        ? []
        : [
            {
              org_slug: "msp-2025",
              org_name: "МСПИН 2025",
              jobs_concurrent: 4,
              jobs_max_duration_s: null,
            },
          ],
  },
  services: servicesFor(seed, now),
  storage: storageFor(seed, now),
  counter: 10,
});
