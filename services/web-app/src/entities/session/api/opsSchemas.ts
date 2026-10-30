import { z } from "zod";

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
  // Личный раннер, когда админ выключил личные раннеры на установке.
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
  // Личные раннеры (этап 4). Необязательные, пока не все бэкенды их отдают:
  // нет поля значит раннер установки.
  owner_kind: z.enum(["instance", "user"]).optional(),
  owner: z
    .strictObject({ id: z.string(), name: z.string(), email: z.string() })
    .nullable()
    .optional(),
  host_kind: z.enum(["cli", "desktop"]).optional(),
  ai_endpoints: z.array(z.string()).optional(),
  last_seen_ip: z.string().nullable().optional(),
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
export type AdminJobPage = { items: AdminJob[]; hasMore: boolean };
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
