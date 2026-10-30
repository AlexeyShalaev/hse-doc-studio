import type {
  BuildRunnersPolicy,
  DeclaredAiEndpoint,
  MyRunner,
  MyRunnerState,
  MyRunnerToken,
  RemoteRunnerStatus,
  RunnerHostKind,
  RunnerPairingInfo,
} from "@entities/runner";
import { DEMO_STUDENT } from "./scenarios";

// Личные раннеры в демо-мире: свои раннеры Анны и раннеры других людей (их видит
// админ), токены регистрации, коды сопряжения, политика сборок проектов, личные
// ИИ-провайдеры и облачные сборки локальной Студии. Формы совпадают с эталонами
// раздела 10 спецификации personal_runners_spec.md (MyRunner, RunnerPairingInfo...).
// Время отсчитывается от создания мира: состояния по last_seen_at выглядят живыми.

/**
 * default: у Анны раннеры во всех состояниях (в сети, давно не отвечал, на паузе,
 * не в сети, отозван), токен и провайдер через раннер;
 * none: раннеров у Анны ещё нет;
 * offline: единственный раннер Анны не в сети, сборки и ИИ идут мимо него;
 * disabled: администратор выключил личные раннеры на всю установку.
 */
export type ServerDemoPersonalSeed =
  "default" | "none" | "offline" | "disabled";

/**
 * Облачные сборки локальной Студии: выключены, в сети или с проблемами
 * (нет Docker и образа TeX).
 */
export type ServerDemoRemoteSeed = "off" | "online" | "docker_missing";

export type DemoRunnerOwner = { id: string; name: string; email: string };

/** Раннер мира: состояние считается по полям, как runner_status на сервере. */
export type DemoPersonalRunner = {
  id: string;
  owner: DemoRunnerOwner;
  name: string;
  host_kind: RunnerHostKind;
  tags: string[];
  concurrency: number;
  ai_concurrency: number;
  version: string;
  created_at: string;
  last_seen_at: string | null;
  last_seen_ip: string | null;
  /** Раннер сам сказал «ухожу» (POST /offline). */
  offline: boolean;
  /** Раннер опрашивает сервер: last_seen_at обновляется при каждом чтении мира. */
  alive: boolean;
  paused: boolean;
  revoked_at: string | null;
  running_jobs: number;
  ai_endpoints: DeclaredAiEndpoint[];
  features: string[];
};

export type DemoRunnerToken = MyRunnerToken & {
  owner_id: string;
  /** Когда раннер «зарегистрируется» по этому токену: так новый раннер появляется сам. */
  registers_at: number | null;
};

export type DemoPairing = RunnerPairingInfo & {
  /** Подтверждение упирается в предел раннеров: 409 personal_runner_limit. */
  hits_limit?: boolean;
};

/** Личный ИИ-провайдер человека (свой ключ или через свой раннер). */
export type DemoOwnProvider = {
  id: string;
  owner_id: string;
  name: string;
  type: "claude" | "openai" | "openai_compat" | "runner";
  base_url: string;
  models: string[];
  has_api_key: boolean;
  created_at: string;
  ssl_verify: boolean;
  connect_timeout_s: number;
  request_timeout_s: number;
  runner_id: string | null;
  runner_endpoint: string | null;
};

/** Локальный провайдер Студии, который можно открыть облаку (вид ollama или openai_compat). */
export type DemoLocalProvider = {
  id: string;
  name: string;
  type: "ollama" | "openai_compat" | "claude";
  base_url: string;
};

export type DemoRemoteRunner = RemoteRunnerStatus & {
  /** Когда ожидание кода само сменится подключением: Студия «увидела» подтверждение. */
  pairing_done_at: number | null;
};

export type DemoPersonal = {
  /** runners.personal_enabled */
  enabled: boolean;
  /** Ключ задан окружением: из админки не меняется. */
  enabledLocked: boolean;
  /** runners.personal_wait_s */
  waitS: number;
  /** runners.personal_max_per_user */
  maxPerUser: number;
  runners: DemoPersonalRunner[];
  tokens: DemoRunnerToken[];
  pairings: Record<string, DemoPairing>;
  /** Политика сборок соавторов по проектам; нет записи значит shared. */
  policies: Record<string, BuildRunnersPolicy>;
  providers: DemoOwnProvider[];
  localProviders: DemoLocalProvider[];
  remote: DemoRemoteRunner;
  counter: number;
};

const SECOND = 1000;
const MINUTE = 60 * SECOND;
const HOUR = 60 * MINUTE;
const DAY = 24 * HOUR;

const ago = (ms: number, now: number): string =>
  new Date(now - ms).toISOString();
const ahead = (ms: number, now: number): string =>
  new Date(now + ms).toISOString();

export const ANNA: DemoRunnerOwner = {
  id: DEMO_STUDENT.id,
  name: DEMO_STUDENT.name,
  email: DEMO_STUDENT.email,
};
export const PAVEL: DemoRunnerOwner = {
  id: "u_01hx7k5pavel",
  name: "Павел Орлов",
  email: "pavel.orlov@example.org",
};
const MARIA: DemoRunnerOwner = {
  id: "u_01hx7k8maria",
  name: "Мария Келлер",
  email: "maria.keller@example.org",
};

const ALL_FEATURES = ["ai_relay", "ai_slots", "announce", "offline"];
export const DEMO_SERVER_URL = "https://studio.example.org";

/** Идентификатор раннера MacBook Анны: на него ссылается провайдер через раннер. */
export const MACBOOK_ID = "4f1c2b3a5d6e47f89a0b1c2d3e4f5a6b";
export const RELAY_PROVIDER_ID = "1b2c3d4e-5f60-4718-293a-4b5c6d7e8f90";
/** Проект Павла, где Анна читатель, а сборки соавторов идут на раннере владельца. */
export const PAVEL_PROJECT_ID = "p_01hxa3k2jm";

const runner = (
  now: number,
  base: Pick<DemoPersonalRunner, "id" | "owner" | "name" | "host_kind"> &
    Partial<DemoPersonalRunner> & { seenMs?: number | null },
): DemoPersonalRunner => {
  const { seenMs = 8 * SECOND, ...rest } = base;
  return {
    tags: ["archive:7z", "pack", "tex"],
    concurrency: 1,
    ai_concurrency: 0,
    version: "0.2.0",
    created_at: ago(9 * DAY, now),
    last_seen_at: seenMs === null ? null : ago(seenMs, now),
    last_seen_ip: "203.0.113.7",
    offline: false,
    alive: seenMs !== null && seenMs <= MINUTE,
    paused: false,
    revoked_at: null,
    running_jobs: 0,
    ai_endpoints: [],
    features: ALL_FEATURES,
    ...rest,
  };
};

const macbook = (now: number, extra: Partial<DemoPersonalRunner> = {}) =>
  runner(now, {
    id: MACBOOK_ID,
    owner: ANNA,
    name: "MacBook Анны",
    host_kind: "desktop",
    tags: ["ai", "archive:7z", "pack", "tex"],
    ai_concurrency: 2,
    running_jobs: 1,
    ai_endpoints: [{ name: "ollama", flavor: "ollama" }],
    created_at: ago(2 * DAY, now),
    ...extra,
  });

/** Раннеры других людей: их видит только админ установки. */
const othersRunners = (now: number): DemoPersonalRunner[] => [
  runner(now, {
    id: "6a7b8c9d0e1f42a3b4c5d6e7f8a9b0c1",
    owner: PAVEL,
    name: "Десктоп Павла",
    host_kind: "desktop",
    seenMs: 15 * SECOND,
    last_seen_ip: "198.51.100.24",
  }),
  runner(now, {
    id: "7b8c9d0e1f2a43b4c5d6e7f8a9b0c1d2",
    owner: MARIA,
    name: "gpu-box",
    host_kind: "cli",
    concurrency: 2,
    ai_concurrency: 4,
    tags: ["ai", "pack", "tex"],
    ai_endpoints: [
      { name: "vllm", flavor: "openai" },
      { name: "ollama", flavor: "ollama" },
    ],
    seenMs: 40 * SECOND,
    last_seen_ip: "192.0.2.51",
    running_jobs: 2,
  }),
];

const annaRunners = (
  seed: ServerDemoPersonalSeed,
  now: number,
): DemoPersonalRunner[] => {
  if (seed === "none") return [];
  if (seed === "offline") {
    return [
      macbook(now, {
        last_seen_at: ago(2 * HOUR, now),
        offline: true,
        alive: false,
        running_jobs: 0,
      }),
    ];
  }
  return [
    macbook(now),
    runner(now, {
      id: "5e6f7a8b9c0d41e2f3a4b5c6d7e8f9a0",
      owner: ANNA,
      name: "Домашний сервер",
      host_kind: "cli",
      concurrency: 2,
      ai_concurrency: 2,
      tags: ["ai", "pack", "tex"],
      ai_endpoints: [{ name: "vllm", flavor: "openai" }],
      paused: true,
      seenMs: 20 * SECOND,
      last_seen_ip: "198.51.100.8",
    }),
    runner(now, {
      id: "3d4e5f6a7b8c49d0e1f2a3b4c5d6e7f8",
      owner: ANNA,
      name: "Рабочий ПК",
      host_kind: "desktop",
      seenMs: 3 * MINUTE,
    }),
    runner(now, {
      id: "2c3d4e5f6a7b48c9d0e1f2a3b4c5d6e7",
      owner: ANNA,
      name: "Старый ноутбук",
      host_kind: "cli",
      version: "0.1.4",
      features: [],
      seenMs: 2 * DAY,
      last_seen_ip: null,
    }),
    runner(now, {
      id: "1b2c3d4e5f6a47b8c9d0e1f2a3b4c5d6",
      owner: ANNA,
      name: "Ноутбук в общежитии",
      host_kind: "cli",
      seenMs: 6 * DAY,
      revoked_at: ago(5 * DAY, now),
    }),
  ];
};

const annaTokens = (
  seed: ServerDemoPersonalSeed,
  now: number,
): DemoRunnerToken[] =>
  seed === "default"
    ? [
        {
          id: "8a7b6c5d4e3f40112233445566778899",
          label: "Сервер на даче",
          created_at: ago(HOUR, now),
          expires_at: ahead(23 * HOUR, now),
          used: false,
          revoked: false,
          owner_id: ANNA.id,
          registers_at: null,
        },
      ]
    : [];

const pairing = (
  now: number,
  code: string,
  extra: Partial<DemoPairing> = {},
): DemoPairing => ({
  user_code: code,
  name: "Ноутбук Анны",
  host_kind: "desktop",
  requested_at: ago(2 * MINUTE, now),
  expires_at: ahead(8 * MINUTE, now),
  client_ip: "203.0.113.7",
  status: "pending",
  ...extra,
});

/**
 * Коды сопряжения для страницы подтверждения: BCDF-2345 ждёт решения,
 * LMNP-6789 упирается в предел раннеров, XKCD-7777 истёк, QRST-2468 уже
 * использован. Любой другой правильный код не найден.
 */
const pairings = (now: number): Record<string, DemoPairing> => ({
  "BCDF-2345": pairing(now, "BCDF-2345"),
  "LMNP-6789": pairing(now, "LMNP-6789", {
    name: "Сервер в лаборатории",
    host_kind: "cli",
    client_ip: "192.0.2.77",
    hits_limit: true,
  }),
  "XKCD-7777": pairing(now, "XKCD-7777", {
    requested_at: ago(25 * MINUTE, now),
    expires_at: ago(15 * MINUTE, now),
    status: "expired",
  }),
  "QRST-2468": pairing(now, "QRST-2468", {
    requested_at: ago(HOUR, now),
    expires_at: ago(50 * MINUTE, now),
    status: "approved",
  }),
});

const providers = (
  seed: ServerDemoPersonalSeed,
  now: number,
): DemoOwnProvider[] => {
  const direct: DemoOwnProvider = {
    id: "9c8b7a6d-5e4f-4a3b-8c2d-1e0f9a8b7c6d",
    owner_id: ANNA.id,
    name: "Мой OpenAI",
    type: "openai",
    base_url: "",
    models: ["gpt-4.1-mini", "gpt-4.1"],
    has_api_key: true,
    created_at: ago(20 * DAY, now),
    ssl_verify: true,
    connect_timeout_s: 10,
    request_timeout_s: 60,
    runner_id: null,
    runner_endpoint: null,
  };
  if (seed === "none") return [direct];
  return [
    {
      id: RELAY_PROVIDER_ID,
      owner_id: ANNA.id,
      name: "Ollama на ноутбуке",
      type: "runner",
      base_url: "",
      models: ["qwen2.5:7b", "llama3.1:8b"],
      has_api_key: false,
      created_at: ago(DAY, now),
      ssl_verify: true,
      connect_timeout_s: 10,
      request_timeout_s: 120,
      runner_id: MACBOOK_ID,
      runner_endpoint: "ollama",
    },
    direct,
  ];
};

const localProviders = (): DemoLocalProvider[] => [
  {
    id: "6a5b4c3d-2e1f-4a0b-9c8d-7e6f5a4b3c2d",
    name: "Ollama",
    type: "ollama",
    base_url: "http://localhost:11434/v1",
  },
  {
    id: "7b6c5d4e-3f2a-4b1c-8d9e-0f1a2b3c4d5e",
    name: "LM Studio",
    type: "openai_compat",
    base_url: "http://192.168.1.20:1234/v1",
  },
  {
    id: "8c7d6e5f-4a3b-4c2d-9e0f-1a2b3c4d5e6f",
    name: "Claude",
    type: "claude",
    base_url: "",
  },
];

const OLLAMA_ENDPOINT = {
  name: "ollama",
  provider_id: "6a5b4c3d-2e1f-4a0b-9c8d-7e6f5a4b3c2d",
  flavor: "ollama" as const,
  url: "http://localhost:11434/v1",
};

export const createRemoteRunner = (
  seed: ServerDemoRemoteSeed,
): DemoRemoteRunner => {
  const off: DemoRemoteRunner = {
    enabled: false,
    server_url: null,
    paired: false,
    runner_id: null,
    runner_name: null,
    state: "off",
    detail_code: null,
    running_jobs: 0,
    concurrency: 1,
    yield_to_local: true,
    docker: "ok",
    tex_image: "ready",
    ai_endpoints: [],
    pairing: null,
    pairing_done_at: null,
  };
  if (seed === "off") return off;
  const online: DemoRemoteRunner = {
    ...off,
    enabled: true,
    server_url: DEMO_SERVER_URL,
    paired: true,
    runner_id: MACBOOK_ID,
    runner_name: "MacBook Анны",
    state: "online",
    running_jobs: 1,
    ai_endpoints: [OLLAMA_ENDPOINT],
  };
  return seed === "online"
    ? online
    : { ...online, running_jobs: 0, docker: "missing", tex_image: "missing" };
};

export const createDemoPersonal = (
  seed: ServerDemoPersonalSeed = "default",
  remoteSeed: ServerDemoRemoteSeed = "off",
): DemoPersonal => {
  const now = Date.now();
  return {
    enabled: seed !== "disabled",
    enabledLocked: false,
    waitS: 5,
    maxPerUser: 5,
    runners: [...annaRunners(seed, now), ...othersRunners(now)],
    tokens: annaTokens(seed, now),
    pairings: pairings(now),
    // Практика Анны собирается на её раннерах и у соавторов; проект Павла тоже.
    policies: { p_01hxa4n7pq: "owner", [PAVEL_PROJECT_ID]: "owner" },
    providers: providers(seed, now),
    localProviders: localProviders(),
    remote: createRemoteRunner(remoteSeed),
    counter: 0,
  };
};

/** Живые раннеры только что опросили сервер: их состояние не стареет, пока открыт мир. */
export const touchRunners = (state: DemoPersonal, now = Date.now()): void => {
  const seen = new Date(now - 4 * SECOND).toISOString();
  for (const r of state.runners) {
    if (r.alive && r.revoked_at === null) r.last_seen_at = seen;
  }
};

// Те же пороги, что у сервера: в сети до минуты тишины, «давно не отвечал» до пяти.
const ONLINE_MS = MINUTE;
const STALE_MS = 5 * MINUTE;

/** Состояние раннера по правилам runner_status (раздел 4.6 спецификации). */
export const runnerState = (
  r: DemoPersonalRunner,
  enabled: boolean,
  now = Date.now(),
): MyRunnerState => {
  if (r.revoked_at !== null) return "revoked";
  if (!enabled) return "disabled";
  if (r.paused) return "paused";
  if (r.offline || r.last_seen_at === null) return "offline";
  const age = now - Date.parse(r.last_seen_at);
  return age <= ONLINE_MS ? "online" : age <= STALE_MS ? "stale" : "offline";
};

export const toMyRunner = (
  r: DemoPersonalRunner,
  enabled: boolean,
): MyRunner => ({
  id: r.id,
  name: r.name,
  state: runnerState(r, enabled),
  host_kind: r.host_kind,
  tags: r.tags,
  concurrency: r.concurrency,
  ai_concurrency: r.ai_concurrency,
  version: r.version,
  created_at: r.created_at,
  last_seen_at: r.last_seen_at,
  last_seen_ip: r.last_seen_ip,
  paused: r.paused,
  revoked: r.revoked_at !== null,
  running_jobs: r.revoked_at === null ? r.running_jobs : 0,
  ai_endpoints: r.ai_endpoints,
  features: r.features,
});

/** Новый раннер, «зарегистрированный» по токену или подтверждённому коду. */
export const registeredRunner = (
  state: DemoPersonal,
  owner: DemoRunnerOwner,
  name: string,
  hostKind: RunnerHostKind,
): DemoPersonalRunner => {
  state.counter += 1;
  const now = Date.now();
  const suffix = String(state.counter).padStart(4, "0");
  return runner(now, {
    id: `9f8e7d6c5b4a43210fedcba98765${suffix}`,
    owner,
    name,
    host_kind: hostKind,
    created_at: new Date(now).toISOString(),
    seenMs: 0,
    tags:
      hostKind === "desktop"
        ? ["ai", "archive:7z", "pack", "tex"]
        : ["pack", "tex"],
    ai_concurrency: hostKind === "desktop" ? 2 : 0,
    ai_endpoints:
      hostKind === "desktop" ? [{ name: "ollama", flavor: "ollama" }] : [],
  });
};
