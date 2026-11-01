import { z } from "zod";

// Контракт `/api/admin/backups` (формы описаны в api/schemas/backups.py).
// Секретов в ответах нет: ключ доступа приходит подсказкой, секретный ключ признаком.

export const DestinationKindSchema = z.enum(["s3", "local"]);
export type DestinationKind = z.infer<typeof DestinationKindSchema>;

export const BackupDestinationSchema = z.object({
  id: z.string(),
  name: z.string(),
  kind: DestinationKindSchema,
  is_default: z.boolean(),
  endpoint: z.string().nullable(),
  region: z.string(),
  bucket: z.string().nullable(),
  prefix: z.string(),
  path_style: z.boolean(),
  local_path: z.string().nullable(),
  access_key_hint: z.string().nullable(),
  secret_key_set: z.boolean(),
  created_at: z.string(),
  updated_at: z.string(),
  last_check_at: z.string().nullable(),
  last_check_ok: z.boolean().nullable(),
  last_check_error: z.string().nullable(),
});
export type BackupDestination = z.infer<typeof BackupDestinationSchema>;
export const BackupDestinationListSchema = z.array(BackupDestinationSchema);

export const CheckResultSchema = z.object({
  ok: z.boolean(),
  error: z.string().nullable(),
  warnings: z.array(z.string()),
  checked_at: z.string(),
});
export type CheckResult = z.infer<typeof CheckResultSchema>;

export const RunStatusSchema = z.enum([
  "running",
  "ok",
  "failed",
  "interrupted",
]);
export type RunStatus = z.infer<typeof RunStatusSchema>;

export const BackupRunSchema = z.object({
  id: z.string(),
  destination_id: z.string().nullable(),
  destination_name: z.string(),
  trigger: z.enum(["manual", "schedule"]),
  status: RunStatusSchema,
  stage: z.string().nullable(),
  started_at: z.string(),
  finished_at: z.string().nullable(),
  duration_s: z.number().nullable(),
  size_bytes: z.number().nullable(),
  backup_id: z.string().nullable(),
  error: z.string().nullable(),
  removed_at: z.string().nullable(),
});
export type BackupRun = z.infer<typeof BackupRunSchema>;

export const BackupRunPageSchema = z.object({
  items: z.array(BackupRunSchema),
  total: z.number(),
  limit: z.number(),
  offset: z.number(),
});
export type BackupRunPage = z.infer<typeof BackupRunPageSchema>;

export const ScheduleKindSchema = z.enum(["interval", "cron"]);
export const EncryptionModeSchema = z.enum(["installation", "passphrase"]);

export const BackupSettingsSchema = z.object({
  enabled: z.boolean(),
  schedule_kind: ScheduleKindSchema,
  interval_hours: z.number(),
  cron: z.string(),
  keep_last: z.number(),
  keep_days: z.number(),
  encryption_mode: EncryptionModeSchema,
  notify_admins: z.boolean(),
  passphrase_set: z.boolean(),
});
export type BackupSettings = z.infer<typeof BackupSettingsSchema>;

export const BackupStatusSchema = z.object({
  settings: BackupSettingsSchema,
  next_run_at: z.string().nullable(),
  last_scheduled_at: z.string().nullable(),
  running: BackupRunSchema.nullable(),
  last_run: BackupRunSchema.nullable(),
  local_root: z.string(),
  destinations_total: z.number(),
});
export type BackupStatus = z.infer<typeof BackupStatusSchema>;

export const StoredBackupSchema = z.object({
  backup_id: z.string(),
  created_at: z.string(),
  app_version: z.string(),
  schema_revision: z.string().nullable(),
  installation_id: z.string().nullable(),
  encryption_mode: EncryptionModeSchema,
  size: z.number(),
  parts: z.array(
    z.object({ name: z.string(), size: z.number(), plain_size: z.number() }),
  ),
  manifest_sha256: z.string(),
  restore_command: z.string(),
});
export type StoredBackup = z.infer<typeof StoredBackupSchema>;
export const StoredBackupListSchema = z.array(StoredBackupSchema);

/** Тело создания и правки назначения. Пустые ключи при правке значат «оставить как есть». */
export type DestinationBody = {
  name: string;
  kind: DestinationKind;
  endpoint: string | null;
  region: string;
  bucket: string | null;
  prefix: string;
  path_style: boolean;
  local_path: string | null;
  access_key: string | null;
  secret_key: string | null;
  make_default: boolean;
};

export type SettingsBody = Omit<BackupSettings, "passphrase_set"> & {
  passphrase: string | null;
};
