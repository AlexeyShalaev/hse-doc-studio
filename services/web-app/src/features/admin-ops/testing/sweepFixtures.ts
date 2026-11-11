import type {
  LifecycleSweep,
  LifecycleSweepPreview,
  LifecycleSweepStep,
} from "@entities/session";

// Эталоны и состояния «Освободить место» (docs/design/storage-cleanup.md, 4.3, 4.5, 5.4 и 9.2).
// Время постоянное, чтобы галереи не плыли. Срез B7 перенесёт LIFECYCLE_SWEEP_CONTRACT_EXAMPLES
// в contracts/server/fixtures/<Схема>/<вариант>.json.

export const SWEEP_NOW = "2026-11-11T10:00:00Z";
const NOW_MS = Date.parse(SWEEP_NOW);
const at = (secondsAgo: number): string =>
  new Date(NOW_MS - secondsAgo * 1000).toISOString().replace(".000Z", "Z");
const daysAgo = (days: number) => at(days * 86400);

const MIB = 1024 ** 2;

/** Ручные источники движка в порядке реестра core/lifecycle/policies.py (стратегия движка и run_now). */
export const SWEEP_SOURCE_KEYS = [
  "ai_usage",
  "jobs",
  "notifications",
  "collab_requests",
  "share_links",
  "guest_sessions",
  "collab_state",
] as const;

/** Сроки по умолчанию; у гостевых сессий срок фиксированный (истекшие). */
export const SWEEP_SOURCE_DAYS: Record<string, number | null> = {
  ai_usage: 90,
  jobs: 30,
  notifications: 90,
  collab_requests: 90,
  share_links: 180,
  guest_sessions: null,
  collab_state: 90,
};

export const SWEEP_EXCLUDED: LifecycleSweepPreview["excluded"] = [
  { key: "audit_log", reason: "protected" },
  { key: "auth_records", reason: "own_task" },
  { key: "deleted_projects", reason: "own_task" },
  { key: "blobs", reason: "own_task" },
  { key: "orphans", reason: "own_task" },
  { key: "usage_counters", reason: "own_task" },
  { key: "compile_records", reason: "on_write" },
  { key: "project_artifacts", reason: "on_write" },
  { key: "chat_history", reason: "on_write" },
  { key: "container_logs", reason: "infra" },
  { key: "process_logs", reason: "infra" },
  { key: "postgres_wal", reason: "infra" },
];

type PreviewSource = LifecycleSweepPreview["sources"][number];

const source = (
  key: string,
  count: number | null,
  bytes: number | null,
  extra: Partial<PreviewSource> = {},
): PreviewSource => {
  const days = SWEEP_SOURCE_DAYS[key] ?? null;
  return {
    key,
    days,
    cutoff: days === null ? SWEEP_NOW : daysAgo(days),
    count,
    capped: false,
    bytes,
    ...extra,
  };
};

export const makeSweepPreview = (
  overrides: Partial<LifecycleSweepPreview> = {},
): LifecycleSweepPreview => ({
  sources: [
    source("ai_usage", 77_564, 412 * MIB),
    source("jobs", 1_200, 96 * MIB),
    source("notifications", 0, 18 * MIB),
    source("collab_requests", 3, 1 * MIB),
    source("share_links", 0, 2 * MIB),
    source("guest_sessions", 44, 3 * MIB),
    source("collab_state", 12, 140 * MIB),
  ],
  excluded: SWEEP_EXCLUDED.map((e) => ({ ...e })),
  nothing: false,
  ...overrides,
});

/** Состояния предпросмотра для галереи (4.5): обычный, «нечего», с потолком и без счёта. */
export const SWEEP_PREVIEWS = {
  default: makeSweepPreview(),
  nothing: makeSweepPreview({
    sources: SWEEP_SOURCE_KEYS.map((key) => source(key, 0, 4 * MIB)),
    nothing: true,
  }),
  capped: makeSweepPreview({
    sources: [
      source("ai_usage", 100_000, 9_800 * MIB, { capped: true }),
      source("jobs", 100_000, 2_100 * MIB, { capped: true }),
      source("notifications", 8_310, 64 * MIB),
      source("collab_requests", 0, 1 * MIB),
      // Счёт не уложился в 3 с: «не удалось посчитать».
      source("share_links", null, 12 * MIB),
      source("guest_sessions", 1_204, 9 * MIB),
      source("collab_state", 312, 2_400 * MIB),
    ],
  }),
} satisfies Record<string, LifecycleSweepPreview>;

const step = (
  key: string,
  status: LifecycleSweepStep["status"],
  extra: Partial<LifecycleSweepStep> = {},
): LifecycleSweepStep => ({
  key,
  status,
  removed: 0,
  partitions_dropped: 0,
  more: false,
  bytes_before: null,
  bytes_after: null,
  error: null,
  ...extra,
});

const DONE_STEPS: LifecycleSweepStep[] = [
  step("ai_usage", "done", {
    removed: 77_564,
    partitions_dropped: 2,
    bytes_before: 412 * MIB,
    bytes_after: 236 * MIB,
  }),
  step("jobs", "done", {
    removed: 1_200,
    bytes_before: 96 * MIB,
    bytes_after: 96 * MIB,
  }),
  step("notifications", "done", {
    bytes_before: 18 * MIB,
    bytes_after: 18 * MIB,
  }),
  step("collab_requests", "done", {
    removed: 3,
    bytes_before: 1 * MIB,
    bytes_after: 1 * MIB,
  }),
  step("share_links", "done", {
    bytes_before: 2 * MIB,
    bytes_after: 2 * MIB,
  }),
  step("guest_sessions", "done", {
    removed: 44,
    bytes_before: 3 * MIB,
    bytes_after: 3 * MIB,
  }),
  step("collab_state", "done", {
    removed: 12,
    bytes_before: 140 * MIB,
    bytes_after: 128 * MIB,
  }),
];

const sum = (values: number[]) => values.reduce((a, b) => a + b, 0);
const freedOf = (steps: LifecycleSweepStep[]) =>
  sum(
    steps.map((s) =>
      s.bytes_before !== null && s.bytes_after !== null
        ? Math.max(0, s.bytes_before - s.bytes_after)
        : 0,
    ),
  );

export const makeSweep = (
  overrides: Partial<LifecycleSweep> = {},
): LifecycleSweep => {
  const steps = overrides.steps ?? DONE_STEPS;
  return {
    id: "lsw_01hz5a9c3k",
    status: "done",
    started_by: { id: "u_01hx7k0adm", name: "Алексей Шалаев" },
    started_at: at(300),
    updated_at: at(240),
    finished_at: at(240),
    steps,
    removed_total: sum(steps.map((s) => s.removed)),
    freed_bytes: freedOf(steps),
    ...overrides,
  };
};

const runningSteps = (
  doneCount: number,
  current: LifecycleSweepStep["status"] = "running",
): LifecycleSweepStep[] =>
  DONE_STEPS.map((s, index) =>
    index < doneCount
      ? s
      : index === doneCount
        ? step(s.key, current, { bytes_before: s.bytes_before })
        : step(s.key, "pending"),
  );

/** Состояния прогона для галереи (4.5) и тестов экранов. */
export const SWEEP_STATES = {
  running: makeSweep({
    status: "running",
    steps: runningSteps(2),
    updated_at: at(2),
    finished_at: null,
  }),
  cancelling: makeSweep({
    status: "cancelling",
    steps: runningSteps(3),
    updated_at: at(1),
    finished_at: null,
  }),
  done: makeSweep(),
  /** Бюджет источника кончился: часть записей удалится на плановом тике. */
  done_more: makeSweep({
    steps: DONE_STEPS.map((s) =>
      s.key === "ai_usage" ? { ...s, removed: 250_000, more: true } : s,
    ),
  }),
  error: makeSweep({
    status: "error",
    steps: DONE_STEPS.map((s) =>
      s.key === "jobs"
        ? {
            ...s,
            status: "error" as const,
            removed: 0,
            bytes_after: null,
            error: "canceling statement due to statement timeout",
          }
        : s,
    ),
  }),
  cancelled: makeSweep({
    status: "cancelled",
    steps: DONE_STEPS.map((s, index) =>
      index < 3 ? s : step(s.key, "skipped"),
    ),
  }),
  /** Сервер перезапустился посреди прогона. */
  interrupted: makeSweep({
    status: "interrupted",
    steps: runningSteps(4),
    updated_at: at(900),
    finished_at: at(600),
  }),
} satisfies Record<string, LifecycleSweep>;
export type SweepStateId = keyof typeof SWEEP_STATES;

/**
 * Эталоны раздела 9.2 по имени схемы и варианту: будущие
 * contracts/server/fixtures/<Схема>/<вариант>.json. Ключи совпадают с LIFECYCLE_SWEEP_CONTRACT_SCHEMAS.
 */
export const LIFECYCLE_SWEEP_CONTRACT_EXAMPLES: Record<
  string,
  Record<string, unknown>
> = {
  LifecycleSweepPreview: SWEEP_PREVIEWS,
  LifecycleSweep: {
    running: SWEEP_STATES.running,
    done: SWEEP_STATES.done,
    error: SWEEP_STATES.error,
    interrupted: SWEEP_STATES.interrupted,
  },
  LifecycleSweepState: {
    none: { sweep: null },
    running: { sweep: SWEEP_STATES.running },
  },
};
