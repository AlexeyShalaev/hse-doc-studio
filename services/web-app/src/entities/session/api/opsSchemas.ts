import { z } from "zod";

// Операционные экраны админки: раннеры, очередь, квоты, сервисы, место. Формы совпадают с
// contracts/server/fixtures и pydantic-моделями api/schemas/runner_admin.py и admin_ops.py.

const iso = z.string().min(1);

export const AdminRunnerSchema = z.strictObject({
  id: z.string(),
  name: z.string(),
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

export const JobStateSchema = z.enum([
  "queued",
  "running",
  "succeeded",
  "failed",
  "cancelled",
  "timed_out",
]);
export const AdminJobSchema = z.strictObject({
  id: z.string(),
  kind: z.string(),
  status: JobStateSchema,
  priority: z.enum(["interactive", "checks", "batch"]),
  project_id: z.string().nullable(),
  project_name: z.string().nullable(),
  user_id: z.string(),
  user_name: z.string(),
  tags: z.array(z.string()),
  runner_id: z.string().nullable(),
  runner_name: z.string().nullable(),
  attempt: z.number().int(),
  max_attempts: z.number().int(),
  created_at: iso,
  started_at: iso.nullable(),
  finished_at: iso.nullable(),
  wait_s: z.number().int(),
  error: z.string().nullable(),
});
export const AdminJobPageSchema = z.strictObject({
  items: z.array(AdminJobSchema),
  total: z.number().int(),
});
export const AdminQueueSummarySchema = z.strictObject({
  queued: z.number().int(),
  running: z.number().int(),
  oldest_queued_age_s: z.number().int().nullable(),
  wait_p50_s: z.number().int().nullable(),
  wait_p95_s: z.number().int().nullable(),
  tags: z.array(
    z.strictObject({
      tag: z.string(),
      queued: z.number().int(),
      running: z.number().int(),
      avg_wait_s: z.number().int().nullable(),
    }),
  ),
});

const QuotaSettingStateSchema = z.strictObject({
  source: z.enum(["env", "admin", "default"]),
  locked: z.boolean(),
});
export const AdminQuotaOverrideSchema = z.strictObject({
  org_slug: z.string(),
  org_name: z.string(),
  jobs_concurrent: z.number().int().nullable(),
  jobs_max_duration_s: z.number().int().nullable(),
});
export const AdminQuotasSchema = z.strictObject({
  jobs_concurrent: z.number().int(),
  jobs_max_duration_s: z.number().int(),
  fields: z.record(z.string(), QuotaSettingStateSchema),
  overrides: z.array(AdminQuotaOverrideSchema),
});
export const UpdateAdminQuotasRequestSchema = z.strictObject({
  jobs_concurrent: z.number().int().min(1).max(64).nullable().optional(),
  jobs_max_duration_s: z
    .number()
    .int()
    .min(30)
    .max(86400)
    .nullable()
    .optional(),
});
export const SetAdminQuotaOverrideRequestSchema = z.strictObject({
  jobs_concurrent: z.number().int().min(1).max(64).nullable().optional(),
  jobs_max_duration_s: z
    .number()
    .int()
    .min(30)
    .max(86400)
    .nullable()
    .optional(),
});

export const ServiceStatusSchema = z.enum([
  "ok",
  "degraded",
  "down",
  "unconfigured",
]);
export const AdminServiceSchema = z.strictObject({
  id: z.string(),
  kind: z.enum([
    "database",
    "storage",
    "languagetool",
    "onlyoffice",
    "runners",
    "smtp",
  ]),
  status: ServiceStatusSchema,
  latency_ms: z.number().int().nullable(),
  detail: z.string().nullable(),
  checked_at: iso,
  replicas: z.array(
    z.strictObject({
      name: z.string(),
      status: ServiceStatusSchema,
      latency_ms: z.number().int().nullable(),
      slots_used: z.number().int().nullable(),
      slots_total: z.number().int().nullable(),
    }),
  ),
});
export const AdminStorageSchema = z.strictObject({
  total_bytes: z.number().int(),
  free_bytes: z.number().int().nullable(),
  volume_bytes: z.number().int(),
  object_bytes: z.number().int(),
  computed_at: iso,
  owners: z.array(
    z.strictObject({
      kind: z.enum(["user", "org"]),
      id: z.string(),
      name: z.string(),
      bytes: z.number().int(),
      projects: z.number().int(),
    }),
  ),
});

export type AdminRunner = z.infer<typeof AdminRunnerSchema>;
export type AdminRunnerToken = z.infer<typeof AdminRunnerTokenSchema>;
export type CreateAdminRunnerTokenRequest = z.infer<
  typeof CreateAdminRunnerTokenRequestSchema
>;
export type AdminRunnerTokenCreated = z.infer<
  typeof AdminRunnerTokenCreatedSchema
>;
export type AdminRunnerRotated = z.infer<typeof AdminRunnerRotatedSchema>;
export type JobState = z.infer<typeof JobStateSchema>;
export type AdminJob = z.infer<typeof AdminJobSchema>;
export type AdminJobPage = z.infer<typeof AdminJobPageSchema>;
export type AdminQueueSummary = z.infer<typeof AdminQueueSummarySchema>;
export type AdminQuotaOverride = z.infer<typeof AdminQuotaOverrideSchema>;
export type AdminQuotas = z.infer<typeof AdminQuotasSchema>;
export type UpdateAdminQuotasRequest = z.infer<
  typeof UpdateAdminQuotasRequestSchema
>;
export type ServiceStatus = z.infer<typeof ServiceStatusSchema>;
export type AdminService = z.infer<typeof AdminServiceSchema>;
export type AdminStorage = z.infer<typeof AdminStorageSchema>;
