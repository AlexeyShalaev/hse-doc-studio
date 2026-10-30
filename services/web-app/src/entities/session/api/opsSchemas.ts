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
/** Пикер: первые совпадения поиска; has_more просит уточнить запрос. */
export const AdminPickerOptionSchema = z.strictObject({
  kind: z.string(),
  id: z.string(),
  name: z.string(),
  detail: z.string().nullable(),
});
export const AdminPickerPageSchema = z.strictObject({
  items: z.array(AdminPickerOptionSchema),
  has_more: z.boolean(),
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
export type AdminRunnerPage = z.infer<typeof AdminRunnerPageSchema>;
export type AdminRunnerTokenPage = z.infer<typeof AdminRunnerTokenPageSchema>;
export type AdminRunnerSummary = z.infer<typeof AdminRunnerSummarySchema>;
export type AdminPickerOption = z.infer<typeof AdminPickerOptionSchema>;
export type AdminPickerPage = z.infer<typeof AdminPickerPageSchema>;
