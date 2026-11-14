import type {
  CommandProgress,
  DiskImageCategory,
  DiskOldItem,
  DiskStep,
  DiskTarget,
  DiskUnusedImage,
  DockerDisk,
  RunnerCacheDisk,
  RunnerDiskAuto,
  RunnerDiskAutoLast,
  RunnerDiskCommand,
  RunnerDiskReport,
  RunnerDiskSummary,
  RunnerDiskView,
} from "../model/runnerDisk.schema";

// Состояния диска раннера для галерей, моков и тестов экранов (docs/design/storage-cleanup.md, разделы
// 4.1, 4.5, 5 и 9.1). Время постоянное: экраны галерей и снимки не плывут. Эталоны контракта лежат в
// contracts/server/fixtures/RunnerDisk* и совпадают с этими состояниями (тест в runnerDisk.schema.test.ts).

export const DISK_NOW = "2026-11-11T10:00:00Z";
const NOW_MS = Date.parse(DISK_NOW);
const at = (secondsAgo: number): string =>
  new Date(NOW_MS - secondsAgo * 1000).toISOString().replace(".000Z", "Z");

export const MIB = 1024 ** 2;
export const GIB = 1024 ** 3;
const gib = (value: number): number => Math.round(value * GIB);

export const DISK_MIN_VERSION = "0.22.0";
export const DISK_RUNNER_VERSION = "0.22.1";
const IMAGE = "ghcr.io/alexeyshalaev/hse-doc-studio";

export const DISK_RUNNER_ID = "rn_01hxb1";
export const DISK_ADMIN = { id: "u_01hx7k0adm", name: "Алексей Шалаев" };
export const DISK_OWNER = { id: "u_01hx7k8maria", name: "Мария Келлер" };

/**
 * Что лежит в Docker раннера: из этого собирается Docker-часть отчёта, а демо после очистки
 * вычитает удалённое. Категории полосы и итоги считаются по одним правилам (5.1).
 */
export type DiskInventory = {
  current_version: string;
  /** Образы, которые раннер использует: их не трогает ни одна цель. */
  active: { category: DiskImageCategory; bytes: number }[];
  old: (DiskOldItem & { category: DiskImageCategory })[];
  rollback: (DiskOldItem & { category: DiskImageCategory }) | null;
  unused: DiskUnusedImage[];
  build_cache: { bytes: number; reclaimable_bytes: number; count: number };
  dangling: { bytes: number; count: number };
  stopped_containers: { bytes: number; count: number };
  volumes: { name: string; size_bytes: number }[];
};

export const makeDiskInventory = (
  overrides: Partial<DiskInventory> = {},
): DiskInventory => ({
  current_version: DISK_RUNNER_VERSION,
  active: [
    { category: "compile", bytes: gib(4.6) },
    { category: "languagetool", bytes: gib(0.58) },
    { category: "office", bytes: gib(0.42) },
    { category: "app", bytes: gib(1.12) },
  ],
  old: [
    {
      kind: "studio_image",
      ref: `${IMAGE}:0.20.3`,
      version: "0.20.3",
      size_bytes: gib(1.08),
      category: "app",
    },
    {
      kind: "studio_image",
      ref: `${IMAGE}:0.19.0`,
      version: "0.19.0",
      size_bytes: gib(1.05),
      category: "app",
    },
    {
      kind: "container",
      ref: "hse-runner-0.19.0",
      version: "0.19.0",
      size_bytes: 48 * MIB,
      category: "app",
    },
  ],
  rollback: {
    kind: "studio_image",
    ref: `${IMAGE}:0.21.4`,
    version: "0.21.4",
    size_bytes: gib(1.1),
    category: "app",
  },
  unused: [
    {
      ref: "texlive/texlive:TL2024-historic",
      category: "compile",
      size_bytes: gib(4.3),
    },
    {
      ref: "erikvl87/languagetool:6.4",
      category: "languagetool",
      size_bytes: gib(0.55),
    },
  ],
  build_cache: {
    bytes: gib(2.4),
    reclaimable_bytes: gib(2.1),
    count: 37,
  },
  dangling: { bytes: 612 * MIB, count: 5 },
  stopped_containers: { bytes: 96 * MIB, count: 2 },
  volumes: [
    { name: "hse-texlive-cache", size_bytes: gib(1.3) },
    { name: "hse-ollama-models", size_bytes: gib(4.7) },
  ],
  ...overrides,
});

/** Пустой Docker: всё уже вычищено, остались только используемые образы и тома. */
export const makeCleanDiskInventory = (
  overrides: Partial<DiskInventory> = {},
): DiskInventory =>
  makeDiskInventory({
    old: [],
    rollback: null,
    unused: [],
    build_cache: { bytes: 0, reclaimable_bytes: 0, count: 0 },
    dangling: { bytes: 0, count: 0 },
    stopped_containers: { bytes: 0, count: 0 },
    ...overrides,
  });

const sum = (values: number[]): number =>
  values.reduce((acc, value) => acc + value, 0);
const strip = ({
  category: _category,
  ...item
}: DiskOldItem & { category: DiskImageCategory }): DiskOldItem => item;

/**
 * Docker-часть отчёта из содержимого. `cleanable_bytes` это ровно то, что освободит
 * «Очистить всё» (откат не входит); `unused_images` не повторяет старые версии и откат.
 */
export const dockerDiskOf = (inv: DiskInventory): DockerDisk => {
  const images = [
    ...inv.active,
    ...inv.old
      .filter((o) => o.kind !== "container")
      .map((o) => ({ category: o.category, bytes: o.size_bytes })),
    ...(inv.rollback
      ? [{ category: inv.rollback.category, bytes: inv.rollback.size_bytes }]
      : []),
    ...inv.unused.map((u) => ({ category: u.category, bytes: u.size_bytes })),
  ];
  const byCategory = (key: DiskImageCategory) =>
    sum(images.filter((i) => i.category === key).map((i) => i.bytes));
  const oldContainers = sum(
    inv.old.filter((o) => o.kind === "container").map((o) => o.size_bytes),
  );
  const runtime =
    inv.dangling.bytes +
    inv.stopped_containers.bytes +
    oldContainers +
    sum(inv.volumes.map((v) => v.size_bytes));
  const categories = [
    ...(["compile", "languagetool", "office", "ai", "app"] as const).map(
      (key) => ({ key, bytes: byCategory(key) }),
    ),
    { key: "cache" as const, bytes: inv.build_cache.bytes },
    { key: "runtime" as const, bytes: runtime },
  ].filter((c) => c.bytes > 0);
  const oldReclaimable = sum(inv.old.map((o) => o.size_bytes));
  const unusedBytes = sum(inv.unused.map((u) => u.size_bytes));
  return {
    available: true,
    categories,
    total_bytes: sum(categories.map((c) => c.bytes)),
    cleanable_bytes:
      oldReclaimable +
      unusedBytes +
      inv.build_cache.reclaimable_bytes +
      inv.dangling.bytes +
      inv.stopped_containers.bytes,
    build_cache: { ...inv.build_cache },
    dangling: { ...inv.dangling },
    stopped_containers: { ...inv.stopped_containers },
    unused_images: inv.unused.map((u) => ({ ...u })),
    unused_truncated: false,
    old_versions: {
      current_version: inv.current_version,
      rollback: inv.rollback ? strip(inv.rollback) : null,
      items: inv.old.map(strip),
      reclaimable_bytes: oldReclaimable,
      rollback_bytes: inv.rollback?.size_bytes ?? 0,
    },
    volumes: inv.volumes.map((v) => ({ ...v })),
  };
};

/** Docker не ответил (`available: false`): числа 0, списки пусты, версия раннера остаётся. */
export const unavailableDockerDisk = (
  currentVersion = DISK_RUNNER_VERSION,
): DockerDisk => ({
  available: false,
  categories: [],
  total_bytes: 0,
  cleanable_bytes: 0,
  build_cache: { bytes: 0, reclaimable_bytes: 0, count: 0 },
  dangling: { bytes: 0, count: 0 },
  stopped_containers: { bytes: 0, count: 0 },
  unused_images: [],
  unused_truncated: false,
  old_versions: {
    current_version: currentVersion,
    rollback: null,
    items: [],
    reclaimable_bytes: 0,
    rollback_bytes: 0,
  },
  volumes: [],
});

export const makeRunnerCacheDisk = (
  overrides: Partial<RunnerCacheDisk> = {},
): RunnerCacheDisk => ({
  blobs: { bytes: gib(1.4), count: 2318, limit_bytes: 2 * GIB },
  workspaces: {
    bytes: gib(6.2),
    count: 41,
    limit_bytes: 20 * GIB,
    busy: 1,
  },
  ...overrides,
});

export const emptyRunnerCacheDisk = (): RunnerCacheDisk =>
  makeRunnerCacheDisk({
    blobs: { bytes: 0, count: 0, limit_bytes: 2 * GIB },
    workspaces: { bytes: 0, count: 0, limit_bytes: 20 * GIB, busy: 0 },
  });

/** Цели, которые умеет Docker-раннер с ответившим Docker. */
export const DOCKER_TARGETS: DiskTarget[] = [
  "old_versions",
  "unused_images",
  "build_cache",
  "dangling_images",
  "stopped_containers",
  "runner_cache",
];

/** Отчёт Docker-раннера: полный замер, есть что освободить. */
export const makeRunnerDiskReport = (
  overrides: Partial<RunnerDiskReport> = {},
): RunnerDiskReport => ({
  measured_at: at(40 * 60),
  targets: [...DOCKER_TARGETS],
  docker: dockerDiskOf(makeDiskInventory()),
  docker_reason: null,
  cache: makeRunnerCacheDisk(),
  volume: { total_bytes: 200 * GIB, free_bytes: gib(23.5) },
  ...overrides,
});

/** Раннер в Kubernetes (S6): только кэш файлов, рабочие копии и том данных. */
export const makeKubernetesDiskReport = (
  overrides: Partial<RunnerDiskReport> = {},
): RunnerDiskReport =>
  makeRunnerDiskReport({
    targets: ["runner_cache"],
    docker: null,
    docker_reason: "kubernetes",
    volume: { total_bytes: 20 * GIB, free_bytes: gib(11.8) },
    ...overrides,
  });

/** Локальная Студия как раннер (S7): Docker этого компьютера чистится в самой Студии. */
export const makeDesktopDiskReport = (
  overrides: Partial<RunnerDiskReport> = {},
): RunnerDiskReport =>
  makeRunnerDiskReport({
    targets: ["runner_cache"],
    docker: null,
    docker_reason: "managed_locally",
    cache: makeRunnerCacheDisk({
      blobs: { bytes: 310 * MIB, count: 604, limit_bytes: 2 * GIB },
      workspaces: {
        bytes: gib(1.2),
        count: 9,
        limit_bytes: 20 * GIB,
        busy: 0,
      },
    }),
    volume: { total_bytes: 512 * GIB, free_bytes: 141 * GIB },
    ...overrides,
  });

/** Docker не ответил: Docker-блоки заменены строкой, «Кэш раннера» работает. */
export const makeDockerUnavailableDiskReport = (
  overrides: Partial<RunnerDiskReport> = {},
): RunnerDiskReport =>
  makeRunnerDiskReport({
    targets: ["runner_cache"],
    docker: unavailableDockerDisk(),
    ...overrides,
  });

/** Нечего освобождать: старые версии, кэши и висячие уже вычищены. */
export const makeCleanDiskReport = (
  overrides: Partial<RunnerDiskReport> = {},
): RunnerDiskReport =>
  makeRunnerDiskReport({
    docker: dockerDiskOf(makeCleanDiskInventory()),
    cache: emptyRunnerCacheDisk(),
    volume: { total_bytes: 200 * GIB, free_bytes: gib(41.2) },
    ...overrides,
  });

// Команды и ход.

const step = (
  kind: DiskStep["kind"],
  ref: string | null,
  status: DiskStep["status"],
  freed = 0,
  error: string | null = null,
): DiskStep => ({ kind, ref, status, freed_bytes: freed, error });

/** План «Очистить всё» по отчёту makeRunnerDiskReport, все шаги ещё впереди. */
export const ALL_TARGETS_STEPS: DiskStep[] = [
  step("container", "hse-runner-0.19.0", "pending"),
  step("image", `${IMAGE}:0.20.3`, "pending"),
  step("image", `${IMAGE}:0.19.0`, "pending"),
  step("image", "texlive/texlive:TL2024-historic", "pending"),
  step("image", "erikvl87/languagetool:6.4", "pending"),
  step("dangling_images", null, "pending"),
  step("build_cache", null, "pending"),
  step("runner_blobs", null, "pending"),
  step("runner_workspaces", null, "pending"),
];

const progress = (steps: DiskStep[], error: string | null = null) =>
  ({
    steps,
    freed_bytes: sum(steps.map((s) => s.freed_bytes)),
    error,
  }) satisfies CommandProgress;

const withStatuses = (
  statuses: [DiskStep["status"], number, string | null][],
): DiskStep[] =>
  ALL_TARGETS_STEPS.map((s, index) => {
    const [status, freed, error] = statuses[index] ?? ["pending", 0, null];
    return { ...s, status, freed_bytes: freed, error };
  });

/** Цели автоочистки (раздел 14, A2). */
export const DISK_AUTO_TARGETS: DiskTarget[] = [
  "dangling_images",
  "build_cache",
  "old_versions",
];

export const makeRunnerDiskCommand = (
  overrides: Partial<RunnerDiskCommand> = {},
): RunnerDiskCommand => ({
  id: "rdc_01hz4m2k7q",
  kind: "disk.cleanup",
  state: "queued",
  targets: [...DOCKER_TARGETS],
  include_rollback: false,
  created_at: at(20),
  finished_at: null,
  created_by: DISK_ADMIN,
  progress: null,
  auto: false,
  ...overrides,
});

export const DISK_COMMANDS = {
  queued: makeRunnerDiskCommand(),
  running: makeRunnerDiskCommand({
    state: "running",
    created_at: at(75),
    progress: progress(
      withStatuses([
        ["done", 48 * MIB, null],
        ["done", gib(1.08), null],
        ["running", 0, null],
      ]),
    ),
  }),
  cancelling: makeRunnerDiskCommand({
    state: "cancelling",
    created_at: at(75),
    progress: progress(
      withStatuses([
        ["done", 48 * MIB, null],
        ["done", gib(1.08), null],
        ["running", 0, null],
      ]),
    ),
  }),
  cancelled: makeRunnerDiskCommand({
    state: "cancelled",
    created_at: at(240),
    finished_at: at(180),
    progress: progress(
      withStatuses([
        ["done", 48 * MIB, null],
        ["done", gib(1.08), null],
        ["done", gib(1.05), null],
        ["skipped", 0, null],
        ["skipped", 0, null],
        ["skipped", 0, null],
        ["skipped", 0, null],
        ["skipped", 0, null],
        ["skipped", 0, null],
      ]),
    ),
  }),
  done: makeRunnerDiskCommand({
    state: "done",
    created_at: at(600),
    finished_at: at(420),
    progress: progress(
      withStatuses([
        ["done", 48 * MIB, null],
        ["done", gib(1.08), null],
        ["done", gib(1.05), null],
        ["done", gib(4.3), null],
        ["done", gib(0.55), null],
        ["done", 612 * MIB, null],
        ["done", gib(2.1), null],
        ["done", gib(1.4), null],
        ["done", gib(5.9), null],
      ]),
    ),
  }),
  /** Итог без единого байта: освобождать было нечего. */
  nothing: makeRunnerDiskCommand({
    state: "done",
    targets: ["dangling_images"],
    created_at: at(600),
    finished_at: at(590),
    progress: progress([step("dangling_images", null, "done")]),
  }),
  error: makeRunnerDiskCommand({
    state: "error",
    created_at: at(600),
    finished_at: at(420),
    progress: progress(
      withStatuses([
        ["done", 48 * MIB, null],
        ["done", gib(1.08), null],
        [
          "error",
          0,
          "Error response from daemon: conflict: unable to remove repository reference (must force) - container 3f1a is using its referenced image",
        ],
        ["done", gib(4.3), null],
        ["done", gib(0.55), null],
        ["done", 612 * MIB, null],
        [
          "error",
          0,
          "Error response from daemon: a prune operation is already running",
        ],
        ["done", gib(1.4), null],
        ["done", gib(5.9), null],
      ]),
    ),
  }),
  expired: makeRunnerDiskCommand({
    state: "expired",
    targets: ["build_cache"],
    created_at: at(15 * 60),
    finished_at: at(5 * 60),
  }),
  lost: makeRunnerDiskCommand({
    state: "lost",
    created_at: at(10 * 60),
    finished_at: at(6 * 60),
    progress: progress(
      withStatuses([
        ["done", 48 * MIB, null],
        ["running", 0, null],
      ]),
    ),
  }),
  /** «Обновить»: замер ставится той же командой без целей. */
  measure: makeRunnerDiskCommand({
    id: "rdc_01hz4m3n8r",
    kind: "disk.measure",
    targets: [],
  }),
  /** Автоочистка по порогу места (раздел 14): запустил не человек, цели только безопасные. */
  auto: makeRunnerDiskCommand({
    id: "rdc_01hzauto01",
    state: "running",
    targets: [...DISK_AUTO_TARGETS],
    created_at: at(75),
    created_by: null,
    auto: true,
    progress: progress([
      step("image", `${IMAGE}:0.20.3`, "done", gib(1.08)),
      step("image", `${IMAGE}:0.19.0`, "running"),
      step("dangling_images", null, "pending"),
      step("build_cache", null, "pending"),
    ]),
  }),
} satisfies Record<string, RunnerDiskCommand>;

// Автоочистка общего раннера (14.5).

export const DISK_AUTO_MIN_VERSION = "0.28.0";

/** Последняя автоочистка: шесть часов назад, освобождено 6 ГБ при 8 % свободного. */
export const DISK_AUTO_LAST_DONE: RunnerDiskAutoLast = {
  command_id: "rdc_01hzauto00",
  state: "done",
  started_at: at(6 * 3600 + 20 * 60),
  finished_at: at(6 * 3600 + 18 * 60),
  freed_bytes: gib(6),
  free_bytes: gib(8),
  total_bytes: gib(100),
};

export const makeRunnerDiskAuto = (
  overrides: Partial<RunnerDiskAuto> = {},
): RunnerDiskAuto => ({
  supported: true,
  reason: null,
  min_version: DISK_AUTO_MIN_VERSION,
  enabled: true,
  min_free_percent: 10,
  interval_min: 60,
  last: null,
  ...overrides,
});

// Вид диска (ответ GET .../disk).

export const makeRunnerDiskView = (
  overrides: Partial<RunnerDiskView> = {},
): RunnerDiskView => {
  const report =
    overrides.report === undefined ? makeRunnerDiskReport() : overrides.report;
  return {
    runner_id: DISK_RUNNER_ID,
    supported: true,
    reason: null,
    min_version: DISK_MIN_VERSION,
    online: true,
    last_seen_at: at(6),
    report,
    received_at: report ? at(40 * 60 - 2) : null,
    stale: false,
    command: null,
    measuring: false,
    can_clean: true,
    can_include_rollback: true,
    personal_owner: null,
    auto: makeRunnerDiskAuto(),
    ...overrides,
  };
};

/**
 * Состояния диалога «Диск» для галерей (4.5) и тестов экранов: по одному виду на каждое
 * состояние 4.1. Состояния подтверждений («Очистить всё», откат) строятся на `docker`.
 */
export const RUNNER_DISK_STATES = {
  /** Docker-раннер с полным замером. */
  docker: makeRunnerDiskView({
    auto: makeRunnerDiskAuto({ last: DISK_AUTO_LAST_DONE }),
  }),
  /** Нечего освобождать. */
  nothing_to_clean: makeRunnerDiskView({ report: makeCleanDiskReport() }),
  /** Ждём раннер: команда ещё не забрана. */
  waiting: makeRunnerDiskView({
    command: DISK_COMMANDS.queued,
    can_clean: false,
  }),
  running: makeRunnerDiskView({
    command: DISK_COMMANDS.running,
    can_clean: false,
  }),
  cancelling: makeRunnerDiskView({
    command: DISK_COMMANDS.cancelling,
    can_clean: false,
  }),
  cancelled: makeRunnerDiskView({
    command: DISK_COMMANDS.cancelled,
  }),
  /** Итог: раннер уже прислал новый замер. */
  done: makeRunnerDiskView({
    report: makeCleanDiskReport({ measured_at: at(400) }),
    received_at: at(398),
    command: DISK_COMMANDS.done,
  }),
  done_nothing: makeRunnerDiskView({
    report: makeCleanDiskReport({ measured_at: at(585) }),
    received_at: at(583),
    command: DISK_COMMANDS.nothing,
  }),
  done_error: makeRunnerDiskView({ command: DISK_COMMANDS.error }),
  /** Команда не забрана за 10 минут. */
  expired: makeRunnerDiskView({
    online: false,
    last_seen_at: at(20 * 60),
    command: DISK_COMMANDS.expired,
    can_clean: false,
  }),
  /** Раннер пропал во время очистки. */
  lost: makeRunnerDiskView({
    online: false,
    last_seen_at: at(7 * 60),
    command: DISK_COMMANDS.lost,
    can_clean: false,
  }),
  /** Раннер не на связи: последний замер, очистка и «Обновить» выключены. */
  offline: makeRunnerDiskView({
    auto: makeRunnerDiskAuto({ min_free_percent: 15 }),
    online: false,
    last_seen_at: at(2 * 3600),
    report: makeRunnerDiskReport({ measured_at: at(3 * 3600) }),
    received_at: at(3 * 3600 - 2),
    can_clean: false,
  }),
  /** Раннер ещё не прислал замер; автоочистку на нём выключили переменной. */
  no_report: makeRunnerDiskView({
    report: null,
    auto: makeRunnerDiskAuto({
      supported: false,
      reason: "runner_disabled",
      enabled: false,
    }),
  }),
  /** Замер старше суток. */
  stale: makeRunnerDiskView({
    report: makeRunnerDiskReport({ measured_at: at(30 * 3600) }),
    received_at: at(30 * 3600 - 2),
    stale: true,
  }),
  /** Только что нажали «Обновить»: замер в очереди. */
  measuring: makeRunnerDiskView({ measuring: true }),
  docker_unavailable: makeRunnerDiskView({
    report: makeDockerUnavailableDiskReport(),
  }),
  /** Раннер старой версии: диска нет, экран просит обновить. */
  outdated: makeRunnerDiskView({
    supported: false,
    reason: "outdated",
    report: null,
    can_clean: false,
    can_include_rollback: false,
    auto: makeRunnerDiskAuto({ supported: false, reason: "outdated" }),
  }),
  kubernetes: makeRunnerDiskView({
    report: makeKubernetesDiskReport(),
    can_include_rollback: false,
    auto: makeRunnerDiskAuto({ supported: false, reason: "kubernetes" }),
  }),
  desktop: makeRunnerDiskView({
    report: makeDesktopDiskReport(),
    can_include_rollback: false,
    auto: makeRunnerDiskAuto({ supported: false, reason: "managed_locally" }),
  }),
  /** Идёт автоочистка: запустил не человек, ручная очистка недоступна. */
  auto_running: makeRunnerDiskView({
    command: DISK_COMMANDS.auto,
    can_clean: false,
    auto: makeRunnerDiskAuto({
      last: {
        ...DISK_AUTO_LAST_DONE,
        command_id: DISK_COMMANDS.auto.id,
        state: "delivered",
        started_at: DISK_COMMANDS.auto.created_at,
        finished_at: null,
        freed_bytes: 0,
        free_bytes: gib(7),
      },
    }),
  }),
  /** Личный раннер глазами админа: плашка владельца, флажка отката нет, автоочистки нет. */
  personal_admin: makeRunnerDiskView({
    runner_id: "7b8c9d0e1f2a43b4c5d6e7f8a9b0c1d2",
    can_include_rollback: false,
    personal_owner: DISK_OWNER,
    auto: null,
  }),
  /** Свой раннер в «Моих раннерах»: флажок отката есть, блока автоочистки нет. */
  personal_owner: makeRunnerDiskView({
    runner_id: "5e6f7a8b9c0d41e2f3a4b5c6d7e8f9a0",
    auto: null,
  }),
  /** Свой раннер в «Моих раннерах» после очистки, запущенной админом. */
  personal_owner_done: makeRunnerDiskView({
    runner_id: "5e6f7a8b9c0d41e2f3a4b5c6d7e8f9a0",
    report: makeCleanDiskReport({ measured_at: at(400) }),
    received_at: at(398),
    command: DISK_COMMANDS.done,
    auto: null,
  }),
} satisfies Record<string, RunnerDiskView>;
export type RunnerDiskStateId = keyof typeof RUNNER_DISK_STATES;

export const makeRunnerDiskSummary = (
  overrides: Partial<RunnerDiskSummary> = {},
): RunnerDiskSummary => ({
  reporting: 3,
  outdated: 1,
  min_version: DISK_MIN_VERSION,
  cleanable_bytes: gib(31.6),
  top: [
    {
      runner_id: DISK_RUNNER_ID,
      name: "runner-1",
      cleanable_bytes: gib(23.5),
      measured_at: at(40 * 60),
    },
    {
      runner_id: "rn_01hxb4",
      name: "runner-4",
      cleanable_bytes: gib(5.3),
      measured_at: at(2 * 3600),
    },
    {
      runner_id: "rn_01hxb2",
      name: "runner-2",
      cleanable_bytes: gib(2.8),
      measured_at: at(5 * 3600),
    },
  ],
  ...overrides,
});

/** Ни один общий раннер не сообщает о диске: «обновите их до {version}». */
export const NO_REPORTS_DISK_SUMMARY = makeRunnerDiskSummary({
  reporting: 0,
  outdated: 4,
  cleanable_bytes: 0,
  top: [],
});
