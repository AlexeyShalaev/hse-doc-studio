import { z } from "zod";

// Настройки установки в админке: название и адрес, сборка, политика ключей подписи, общие
// ИИ-провайдеры. Формы совпадают с contracts/server/fixtures и api/schemas/admin_install.py.

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

export const SigningServerKeysSchema = z.enum(["allowed", "forbidden"]);
export const AdminSigningPolicySchema = z.strictObject({
  server_keys: SigningServerKeysSchema,
  stored_keys: z.number().int(),
  fields,
});
export const UpdateAdminSigningPolicyRequestSchema = z.strictObject({
  server_keys: SigningServerKeysSchema.nullable(),
});

export const AdminAiProviderSchema = z.strictObject({
  id: z.string(),
  name: z.string(),
  type: z.enum(["claude", "openai", "openai_compat", "ollama"]),
  base_url: z.string(),
  models: z.array(z.string()),
  has_api_key: z.boolean(),
  created_at: z.string(),
  ssl_verify: z.boolean(),
  connect_timeout_s: z.number(),
  request_timeout_s: z.number(),
  shared: z.literal(true),
});

export type AdminInstanceSettings = z.infer<typeof AdminInstanceSettingsSchema>;
export type UpdateAdminInstanceRequest = z.infer<
  typeof UpdateAdminInstanceRequestSchema
>;
export type AdminBuildSettings = z.infer<typeof AdminBuildSettingsSchema>;
export type UpdateAdminBuildRequest = z.infer<
  typeof UpdateAdminBuildRequestSchema
>;
export type SigningServerKeys = z.infer<typeof SigningServerKeysSchema>;
export type AdminSigningPolicy = z.infer<typeof AdminSigningPolicySchema>;
export type UpdateAdminSigningPolicyRequest = z.infer<
  typeof UpdateAdminSigningPolicyRequestSchema
>;
export type AdminAiProvider = z.infer<typeof AdminAiProviderSchema>;
