import { z } from "zod";

// Квоты по видам ресурсов, использование, переопределения, ИИ-шлюз и автомасштабирование.
// Зеркало api/schemas/quotas.py; эталоны в contracts/server/fixtures (MyUsageResponse,
// AdminQuotaPolicy, AdminAutoscaleStatus...). strictObject повторяет extra=forbid бэкенда.

const iso = z.string().min(1);

export const QUOTA_KINDS = [
  "storage",
  "builds",
  "ai_tokens_day",
  "ai_tokens_month",
  "members",
] as const;
export const QuotaKindSchema = z.enum(QUOTA_KINDS);
export type QuotaKind = z.infer<typeof QuotaKindSchema>;

export const QuotaScopeSchema = z.enum(["user", "org"]);
export type QuotaScope = z.infer<typeof QuotaScopeSchema>;

export const QuotaStateSchema = z.enum([
  "unlimited",
  "ok",
  "warning",
  "exceeded",
]);
export type QuotaState = z.infer<typeof QuotaStateSchema>;

export const OnExceedSchema = z.enum(["deprioritize", "reject", "warn"]);
export type OnExceed = z.infer<typeof OnExceedSchema>;

export const OwnerKindSchema = z.enum(["user", "org"]);
export type OwnerKind = z.infer<typeof OwnerKindSchema>;

export const UsageLineSchema = z.strictObject({
  kind: QuotaKindSchema,
  scope: QuotaScopeSchema,
  unit: z.string(),
  used: z.number().int().nonnegative(),
  limit: z.number().int().nullable(),
  percent: z.number().int().nullable(),
  state: QuotaStateSchema,
  source: z.enum(["user", "org", "installation"]).nullable(),
  resets_at: iso.nullable(),
});
export type UsageLine = z.infer<typeof UsageLineSchema>;

export const OwnerUsageResponseSchema = z.strictObject({
  owner_id: z.string(),
  owner_name: z.string(),
  lines: z.array(UsageLineSchema),
});
export type OwnerUsage = z.infer<typeof OwnerUsageResponseSchema>;

export const MyUsageResponseSchema = z.strictObject({
  user: OwnerUsageResponseSchema,
  orgs: z.array(OwnerUsageResponseSchema),
  warn_percent: z.number().int(),
});
export type MyUsage = z.infer<typeof MyUsageResponseSchema>;

export const AdminQuotaDefaultSchema = z.strictObject({
  kind: QuotaKindSchema,
  user: z.number().int().min(1).nullable(),
  org: z.number().int().min(1).nullable(),
});
export type AdminQuotaDefault = z.infer<typeof AdminQuotaDefaultSchema>;

export const AdminQuotaPolicySchema = z.strictObject({
  defaults: z.array(AdminQuotaDefaultSchema),
  warn_percent: z.number().int().min(1).max(100),
  on_exceed: OnExceedSchema,
});
export type AdminQuotaPolicy = z.infer<typeof AdminQuotaPolicySchema>;
export const UpdateAdminQuotaPolicyRequestSchema = AdminQuotaPolicySchema;

export const QUOTA_RESOURCES = [
  "jobs.concurrent_user",
  "jobs.concurrent_org",
  "jobs.max_duration_s",
  "storage.bytes_user",
  "storage.bytes_org",
  "builds.month_user",
  "builds.month_org",
  "ai.tokens_day_user",
  "ai.tokens_day_org",
  "ai.tokens_month_user",
  "ai.tokens_month_org",
  "members.project_user",
  "members.project_org",
] as const;
export const QuotaResourceSchema = z.enum(QUOTA_RESOURCES);
export type QuotaResource = z.infer<typeof QuotaResourceSchema>;

export const AdminQuotaOverrideSchema = z.strictObject({
  owner_kind: OwnerKindSchema,
  owner_id: z.string(),
  owner_name: z.string(),
  resource: QuotaResourceSchema,
  hard_limit: z.number().int().min(1),
});
export type AdminQuotaOverride = z.infer<typeof AdminQuotaOverrideSchema>;
export const AdminQuotaOverrideListSchema = z.array(AdminQuotaOverrideSchema);

export const SetAdminQuotaOverrideRequestSchema = z.strictObject({
  owner_kind: OwnerKindSchema,
  owner_id: z.string().min(1).max(64),
  resource: QuotaResourceSchema,
  hard_limit: z.number().int().min(1),
});
export type SetAdminQuotaOverrideRequest = z.infer<
  typeof SetAdminQuotaOverrideRequestSchema
>;

export const ResetUsageRequestSchema = z.strictObject({
  owner_kind: OwnerKindSchema,
  owner_id: z.string().min(1).max(64),
  kind: QuotaKindSchema,
});
export type ResetUsageRequest = z.infer<typeof ResetUsageRequestSchema>;

const TopConsumerSchema = z.strictObject({
  user_id: z.string(),
  name: z.string(),
  used: z.number().int(),
});
export type TopConsumer = z.infer<typeof TopConsumerSchema>;

export const AdminUsageSummarySchema = z.strictObject({
  totals: z.partialRecord(QuotaKindSchema, z.number().int()),
  top_builds: z.array(TopConsumerSchema),
  top_ai_tokens: z.array(TopConsumerSchema),
  period_start: z.string(),
  on_exceed: OnExceedSchema,
});
export type AdminUsageSummary = z.infer<typeof AdminUsageSummarySchema>;

export const AdminGatewayProviderSchema = z.strictObject({
  id: z.string(),
  name: z.string(),
  type: z.string(),
  breaker: z.enum(["closed", "open", "half_open"]),
  failures: z.number().int(),
  calls_24h: z.number().int(),
  errors_24h: z.number().int(),
  denied_24h: z.number().int(),
  input_tokens_24h: z.number().int(),
  output_tokens_24h: z.number().int(),
});
export type AdminGatewayProvider = z.infer<typeof AdminGatewayProviderSchema>;
export const AdminGatewayProviderListSchema = z.array(
  AdminGatewayProviderSchema,
);

export const AutoscaleModeSchema = z.enum(["off", "webhook", "compose"]);
export type AutoscaleMode = z.infer<typeof AutoscaleModeSchema>;

export const AdminAutoscalePolicySchema = z.strictObject({
  mode: AutoscaleModeSchema,
  min_runners: z.number().int().min(0).max(200),
  max_runners: z.number().int().min(1).max(200),
  target_queue_per_slot: z.number().min(0.1).max(100),
  scale_up_wait_s: z.number().int().min(0).max(86400),
  cooldown_up_s: z.number().int().min(0).max(86400),
  cooldown_down_s: z.number().int().min(0).max(86400),
  idle_before_down_s: z.number().int().min(0).max(86400),
  step_up: z.number().int().min(1).max(200),
  step_down: z.number().int().min(1).max(200),
  webhook_url: z.string().max(2048).nullable(),
});
export type AdminAutoscalePolicy = z.infer<typeof AdminAutoscalePolicySchema>;

export const SCALE_REASONS = [
  "below_min",
  "above_max",
  "queue_depth",
  "queue_wait",
  "at_max",
  "cooldown_up",
  "idle",
  "idle_wait",
  "cooldown_down",
  "at_min",
  "busy",
  "balanced",
] as const;

export const AdminAutoscaleStatusSchema = z.strictObject({
  policy: AdminAutoscalePolicySchema,
  metrics: z.strictObject({
    queued: z.number().int(),
    oldest_wait_s: z.number(),
    running: z.number().int(),
    runners_online: z.number().int(),
    slots_total: z.number().int(),
    slots_busy: z.number().int(),
  }),
  decision: z.strictObject({
    current: z.number().int(),
    desired: z.number().int(),
    action: z.enum(["hold", "up", "down"]),
    reason: z.enum(SCALE_REASONS),
    wait_s: z.number().int(),
  }),
  last_outcome: z
    .strictObject({
      at: iso,
      desired: z.number().int(),
      ok: z.boolean(),
      error: z.string().nullable(),
    })
    .nullable(),
  last_up_at: iso.nullable(),
  last_down_at: iso.nullable(),
  orchestrator_current: z.number().int().nullable(),
  evaluated_at: iso,
  webhook_secret_set: z.boolean(),
});
export type AdminAutoscaleStatus = z.infer<typeof AdminAutoscaleStatusSchema>;

/** Тело отказа по квоте (429 quota_exceeded и 413 owner_storage_exceeded). */
export const QuotaErrorBodySchema = z.object({
  code: z.enum(["quota_exceeded", "owner_storage_exceeded"]),
  resource: QuotaKindSchema,
  scope: QuotaScopeSchema,
  used: z.number().int(),
  limit: z.number().int(),
  resets_at: iso.nullable(),
});
export type QuotaErrorBody = z.infer<typeof QuotaErrorBodySchema>;
