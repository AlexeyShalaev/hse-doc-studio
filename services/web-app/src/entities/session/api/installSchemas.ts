import { z } from "zod";

// Настройки установки в админке: название и адрес, сборка. Формы совпадают с contracts/server/fixtures
// и api/schemas/admin_install.py. Политика ключей подписи и общие ИИ-провайдеры живут в schemas.ts.

const SettingStateSchema = z.strictObject({
  source: z.enum(["env", "admin", "default"]),
  locked: z.boolean(),
});
const fields = z.record(z.string(), SettingStateSchema);

export const AdminInstanceSettingsSchema = z.strictObject({
  name: z.string(),
  public_url: z.string(),
  docs_url: z.string().nullable(),
  fields,
});
export const UpdateAdminInstanceRequestSchema = z.strictObject({
  name: z.string().nullable(),
  public_url: z.string().nullable(),
  docs_url: z.string().nullable(),
});

export const AdminBuildSettingsSchema = z.strictObject({
  timeout_s: z.number().int(),
  artifact_retention_days: z.number().int(),
  fields,
});
export const UpdateAdminBuildRequestSchema = z.strictObject({
  timeout_s: z.number().int().nullable(),
  artifact_retention_days: z.number().int().nullable(),
});

export type AdminInstanceSettings = z.infer<typeof AdminInstanceSettingsSchema>;
export type UpdateAdminInstanceRequest = z.infer<
  typeof UpdateAdminInstanceRequestSchema
>;
export type AdminBuildSettings = z.infer<typeof AdminBuildSettingsSchema>;
export type UpdateAdminBuildRequest = z.infer<
  typeof UpdateAdminBuildRequestSchema
>;
