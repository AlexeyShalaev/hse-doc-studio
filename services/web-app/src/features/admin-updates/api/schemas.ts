import { z } from "zod";

// Контракт `/api/admin/updates` (формы описаны в api/schemas/server_update.py).

export const PolicySchema = z.enum(["off", "notify", "auto"]);
export type Policy = z.infer<typeof PolicySchema>;
export const MaxBumpSchema = z.enum(["patch", "minor"]);
export const VerifySchema = z.enum(["none", "digest", "cosign"]);

export const UpdateSettingsSchema = z.object({
  policy: PolicySchema,
  channel: z.literal("stable"),
  max_bump: MaxBumpSchema,
  window_days: z.array(z.number().int().min(0).max(6)),
  window_start_min: z.number().int(),
  window_minutes: z.number().int(),
  backup_first: z.boolean(),
  verify: VerifySchema,
  notify_admins: z.boolean(),
});
export type UpdateSettings = z.infer<typeof UpdateSettingsSchema>;

export const ReleaseSchema = z.object({
  version: z.string(),
  date: z.string(),
  notes: z.array(z.string()),
  has_digest: z.boolean(),
});
export type Release = z.infer<typeof ReleaseSchema>;

export const RunStatusSchema = z.enum([
  "waiting_backup",
  "queued",
  "running",
  "succeeded",
  "rolled_back",
  "failed",
  "cancelled",
]);
export type RunStatus = z.infer<typeof RunStatusSchema>;

export const RunEventSchema = z.object({
  seq: z.number().int(),
  at: z.string(),
  phase: z.string(),
  level: z.enum(["info", "warn", "error"]),
  message: z.string(),
});

export const UpdateRunSchema = z.object({
  id: z.string(),
  kind: z.enum(["update", "rollback"]),
  trigger: z.enum(["auto", "manual"]),
  status: RunStatusSchema,
  phase: z.string().nullable(),
  from_version: z.string(),
  to_version: z.string(),
  from_revision: z.string().nullable(),
  to_revision: z.string().nullable(),
  created_at: z.string(),
  started_at: z.string().nullable(),
  finished_at: z.string().nullable(),
  duration_s: z.number().nullable(),
  backup_run_id: z.string().nullable(),
  restore_db: z.boolean(),
  db_restored: z.boolean(),
  error_code: z.string().nullable(),
  error: z.string().nullable(),
  events: z.array(RunEventSchema),
});
export type UpdateRun = z.infer<typeof UpdateRunSchema>;

export const UpdateRunPageSchema = z.object({
  items: z.array(UpdateRunSchema),
  total: z.number().int(),
  limit: z.number().int(),
  offset: z.number().int(),
});
export type UpdateRunPage = z.infer<typeof UpdateRunPageSchema>;

export const UpdateStatusSchema = z.object({
  settings: UpdateSettingsSchema,
  current_version: z.string(),
  executor: z.enum(["compose", "none"]),
  updater_online: z.boolean(),
  updater_seen_at: z.string().nullable(),
  updater_version: z.string().nullable(),
  available: ReleaseSchema.nullable(),
  auto_target: ReleaseSchema.nullable(),
  releases: z.array(ReleaseSchema),
  checked_at: z.string().nullable(),
  check_error: z.string().nullable(),
  in_window: z.boolean(),
  next_window_at: z.string().nullable(),
  backup_destination_configured: z.boolean(),
  active_run: UpdateRunSchema.nullable(),
  last_run: UpdateRunSchema.nullable(),
  rollback_version: z.string().nullable(),
  rollback_needs_restore: z.boolean(),
  manual_command: z.string(),
});
export type UpdateStatus = z.infer<typeof UpdateStatusSchema>;
