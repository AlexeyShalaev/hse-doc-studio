import { z } from "zod";

import { pageOf } from "./schemas";

// Операционные экраны админки. Раннеры и токены разбираются схемами ниже (api/schemas/runner_admin.py).
// Очередь, квоты, сервисы и место приходят в формах api/schemas/admin_ops.py (схемы в schemas.ts),
// а экранам отдаются в видах ниже: имена вместо идентификаторов там, где сервер их не знает.

const iso = z.string().min(1);

export const RunnerStatusSchema = z.enum([
  "online",
  "stale",
  "offline",
  "paused",
  "revoked",
  "disabled",
]);
export const AdminRunnerSchema = z.strictObject({
  id: z.string(),
  name: z.string(),
  status: RunnerStatusSchema,
  tags: z.array(z.string()),
  concurrency: z.number().int(),
  resource_class: z.string(),
  version: z.string(),
  created_at: iso,
  last_seen_at: iso.nullable(),
  paused: z.boolean(),
  revoked: z.boolean(),
  owner_kind: z.enum(["instance", "user"]),
  owner: z
    .strictObject({ id: z.string(), name: z.string(), email: z.string() })
    .nullable(),
  host_kind: z.enum(["cli", "desktop"]),
  ai_endpoints: z.array(z.string()),
  last_seen_ip: z.string().nullable(),
});
export const AdminRunnerTokenSchema = z.strictObject({
  id: z.string(),
  label: z.string(),
  created_at: iso,
  expires_at: iso.nullable(),
  max_uses: z.number().int(),
  uses: z.number().int(),
  revoked: z.boolean(),
});
export const CreateAdminRunnerTokenRequestSchema = z.strictObject({
  label: z.string().max(128),
  ttl_hours: z
    .number()
    .int()
    .min(1)
    .max(24 * 30),
  max_uses: z.number().int().min(1).max(100),
});
export const AdminRunnerTokenCreatedSchema = z.strictObject({
  token: AdminRunnerTokenSchema,
  secret: z.string(),
  command: z.string(),
});
export const AdminRunnerRotatedSchema = z.strictObject({
  runner: AdminRunnerSchema,
  runner_token: z.string(),
  command: z.string(),
});
export const UpdateAdminRunnerRequestSchema = z.strictObject({
  paused: z.boolean(),
});
export const AdminRunnerPageSchema = pageOf(AdminRunnerSchema);
export const AdminRunnerTokenPageSchema = pageOf(AdminRunnerTokenSchema);
/** Счётчики раннеров для KPI; outdated и newest_version только среди неотозванных. */
export const AdminRunnerSummarySchema = z.strictObject({
  online: z.number().int(),
  paused: z.number().int(),
  stale: z.number().int(),
  offline: z.number().int(),
  revoked: z.number().int(),
  outdated: z.number().int(),
  newest_version: z.string().nullable(),
});

export type JobState =
  "queued" | "running" | "succeeded" | "failed" | "cancelled" | "timed_out";
export type AdminJob = {
  id: string;
  kind: string;
  status: JobState;
  priority: string;
  project_id: string | null;
  project_name: string | null;
  user_id: string;
  user_name: string;
  /** Почта того, кто запустил; null, если человека уже нет. */
  user_email?: string | null;
  org_id?: string | null;
  org_name?: string | null;
  tags: string[];
  runner_id: string | null;
  runner_name: string | null;
  attempt: number;
  max_attempts: number;
  created_at: string;
  started_at: string | null;
  finished_at: string | null;
  wait_s: number;
  error: string | null;
  /** Маршрут задачи: shared, personal_first, pinned (ИИ через раннер). */
  route?: string | null;
  /** Кто взял попытку: общий раннер или личный. */
  runner_scope?: "shared" | "personal" | null;
  route_reason?: string | null;
};
/** Страница очереди: курсор непрозрачный, null на последней; оценка числа только без фильтров. */
export type AdminJobPage = {
  items: AdminJob[];
  next_cursor: string | null;
  total_estimate: number | null;
};
export type AdminQueueSummary = {
  queued: number;
  running: number;
  /** Число задач в каждом состоянии: для счётчиков фильтров. */
  by_state: Record<JobState, number>;
  oldest_queued_age_s: number | null;
  wait_p50_s: number | null;
  wait_p95_s: number | null;
  /** Ожидающие задачи по классам приоритета. */
  classes: { name: string; queued: number }[];
};
export type AdminQuotas = {
  user_concurrent: number | null;
  org_concurrent: number | null;
  max_duration_s: number | null;
};
export type UpdateAdminQuotasRequest = AdminQuotas;
export type ServiceStatus = "ok" | "degraded" | "down" | "unconfigured";
export type AdminService = {
  id: string;
  kind:
    "database" | "storage" | "languagetool" | "onlyoffice" | "runners" | "smtp";
  status: ServiceStatus;
  /** Короткая причина сбоя от сервера. */
  detail: string | null;
  /** Для раннеров: сколько в сети из скольких. */
  online: number | null;
  total: number | null;
};
export type AdminStorage = {
  blob_count: number;
  blob_bytes: number;
  projects: number;
  deleted_projects: number;
  free_bytes: number | null;
  volume_total_bytes: number | null;
  computed_at: string | null;
  owners: { id: string; name: string; projects: number }[];
};

export type AdminRunner = z.infer<typeof AdminRunnerSchema>;
export type AdminRunnerToken = z.infer<typeof AdminRunnerTokenSchema>;
export type CreateAdminRunnerTokenRequest = z.infer<
  typeof CreateAdminRunnerTokenRequestSchema
>;
export type AdminRunnerTokenCreated = z.infer<
  typeof AdminRunnerTokenCreatedSchema
>;
export type AdminRunnerRotated = z.infer<typeof AdminRunnerRotatedSchema>;
export type AdminRunnerPage = z.infer<typeof AdminRunnerPageSchema>;
export type AdminRunnerTokenPage = z.infer<typeof AdminRunnerTokenPageSchema>;
export type AdminRunnerSummary = z.infer<typeof AdminRunnerSummarySchema>;

// Хранение данных (api/schemas/lifecycle.py): источники роста, сроки хранения, тома и пороги места.
export const LifecycleLevelSchema = z.enum(["ok", "warning", "critical"]);
export const LifecycleLastRunSchema = z.strictObject({
  at: iso.nullable(),
  duration_ms: z.number().int().nullable(),
  removed: z.number().int().nullable(),
  error: z.string().nullable(),
  runs: z.number().int(),
  total_removed: z.number().int().nullable(),
});
export const LifecycleSourceSchema = z.strictObject({
  key: z.string(),
  group: z.enum(["database", "objects", "disk", "logs"]),
  strategy: z.enum([
    "partition_drop",
    "delete_batches",
    "file_sweep",
    "own_task",
    "on_write",
    "infra",
  ]),
  growth: z.enum(["low", "medium", "high"]),
  days: z.number().int().nullable(),
  days_source: z.enum(["admin", "env", "default", "fixed"]),
  min_days: z.number().int().nullable(),
  max_days: z.number().int().nullable(),
  default_days: z.number().int().nullable(),
  editable: z.boolean(),
  run_now: z.boolean(),
  protected: z.boolean(),
  env: z.string().nullable(),
  bytes: z.number().int().nullable(),
  rows: z.number().int().nullable(),
  partitions: z.number().int().nullable(),
  last_run: LifecycleLastRunSchema.nullable(),
});
export const LifecycleVolumeSchema = z.strictObject({
  name: z.string(),
  used_bytes: z.number().int(),
  total_bytes: z.number().int().nullable(),
  free_bytes: z.number().int().nullable(),
  used_ratio: z.number().nullable(),
  level: LifecycleLevelSchema,
});
export const StorageThresholdsSchema = z.strictObject({
  warn_percent: z.number().int(),
  critical_percent: z.number().int(),
});
export const AdminDataLifecycleSchema = z.strictObject({
  sources: z.array(LifecycleSourceSchema),
  volumes: z.array(LifecycleVolumeSchema),
  thresholds: StorageThresholdsSchema,
  level: LifecycleLevelSchema,
  safe_mode: z.boolean(),
});
export const UpdateLifecycleRetentionRequestSchema = z.strictObject({
  days: z.number().int().nullable(),
});
export const LifecycleRunSchema = z.strictObject({
  key: z.string(),
  removed: z.number().int(),
  partitions_dropped: z.number().int(),
  more: z.boolean(),
  error: z.string().nullable(),
});
export type LifecycleLevel = z.infer<typeof LifecycleLevelSchema>;
export type LifecycleSource = z.infer<typeof LifecycleSourceSchema>;
export type LifecycleVolume = z.infer<typeof LifecycleVolumeSchema>;
export type StorageThresholds = z.infer<typeof StorageThresholdsSchema>;
export type AdminDataLifecycle = z.infer<typeof AdminDataLifecycleSchema>;
export type LifecycleRun = z.infer<typeof LifecycleRunSchema>;

// Самодиагностика (api/schemas/diagnostics.py): проверки со статусом, причиной и подсказкой, итог, пороги.
export const DiagStatusSchema = z.enum(["ok", "warn", "fail"]);
export const DiagCheckSchema = z.strictObject({
  id: z.string(),
  group: z.enum(["data", "compute", "security", "operations"]),
  // null: проверка ещё не выполнялась (свежая установка до первого прохода).
  status: DiagStatusSchema.nullable(),
  reason: z.string().nullable(),
  hint: z.string().nullable(),
  values: z.record(z.string(), z.union([z.string(), z.number()])),
  applicable: z.boolean(),
  checked_at: iso.nullable(),
  status_since: iso.nullable(),
  duration_ms: z.number().int().nullable(),
});
export const DiagThresholdSchema = z.strictObject({
  name: z.string(),
  value: z.number().int(),
  default: z.number().int(),
  min: z.number().int(),
  max: z.number().int(),
});
export const AdminDiagnosticsSchema = z.strictObject({
  overall: DiagStatusSchema,
  enabled: z.boolean(),
  interval_s: z.number(),
  last_tick_at: iso.nullable(),
  checks: z.array(DiagCheckSchema),
  thresholds: z.array(DiagThresholdSchema),
  notify: z.boolean(),
});
export const UpdateDiagnosticsThresholdsRequestSchema = z.strictObject({
  values: z.record(z.string(), z.number().int()),
  notify: z.boolean(),
});
export const RunDiagnosticsRequestSchema = z.strictObject({
  check: z.string().nullable(),
});
export type DiagStatus = z.infer<typeof DiagStatusSchema>;
export type DiagCheck = z.infer<typeof DiagCheckSchema>;
export type DiagThreshold = z.infer<typeof DiagThresholdSchema>;
export type AdminDiagnostics = z.infer<typeof AdminDiagnosticsSchema>;
export type UpdateDiagnosticsThresholdsRequest = z.infer<
  typeof UpdateDiagnosticsThresholdsRequestSchema
>;
