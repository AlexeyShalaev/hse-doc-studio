import { z } from "zod";
import { i18n } from "@shared/lib";

export const AIProviderTypeSchema = z.enum([
  "claude",
  "openai",
  "openai_compat",
  // Auto-managed local runtime (Ollama). Routes through the OpenAI-compatible
  // path; its base_url + models are kept in sync by the backend and it is
  // rendered read-only in the UI (no manual create/edit).
  "ollama",
  // Модель в сети человека через его личный раннер: ни адреса, ни ключа у сервера нет.
  "runner",
]);
export type AIProviderType = z.infer<typeof AIProviderTypeSchema>;

export const AIProviderSourceSchema = z.enum(["own", "org", "instance"]);
export type AIProviderSource = z.infer<typeof AIProviderSourceSchema>;

export const RelayStateSchema = z.enum([
  "ready",
  "runner_offline",
  "runner_paused",
  "runner_revoked",
  "endpoint_missing",
  "disabled",
]);
export type RelayState = z.infer<typeof RelayStateSchema>;

export const AIProviderRelaySchema = z.strictObject({
  runner_id: z.string(),
  runner_name: z.string().nullable(),
  endpoint: z.string(),
  flavor: z.enum(["openai", "ollama"]),
  state: RelayStateSchema,
});
export type AIProviderRelay = z.infer<typeof AIProviderRelaySchema>;

// Server response — note there is no `api_key`: the backend exposes only
// `has_api_key` so the secret never reaches the browser.
export const AIProviderSchema = z.strictObject({
  id: z.string(),
  name: z.string(),
  type: AIProviderTypeSchema,
  base_url: z.string(),
  models: z.array(z.string()),
  has_api_key: z.boolean(),
  created_at: z.string(),
  ssl_verify: z.boolean(),
  connect_timeout_s: z.number(),
  request_timeout_s: z.number(),
  // Общий провайдер установки (серверный режим): ключ задал админ и пользователю он не виден.
  shared: z.boolean().optional(),
  // Откуда провайдер: свой, организации, установки. Локальный режим и старый сервер поле не шлют.
  source: AIProviderSourceSchema.optional(),
  // Через какой раннер идёт провайдер вида `runner` и готова ли ретрансляция.
  relay: AIProviderRelaySchema.nullable().optional(),
});
export type AIProvider = z.infer<typeof AIProviderSchema>;

export const ProviderModelsSchema = z.object({
  models: z.array(z.string()),
});
export type ProviderModels = z.infer<typeof ProviderModelsSchema>;

export const CreateAIProviderSchema = z.object({
  name: z.string().min(1, {
    error: () => i18n.t("entitiesMisc:aiProviderValidation.nameRequired"),
  }),
  type: AIProviderTypeSchema,
  api_key: z.string().min(1, {
    error: () => i18n.t("entitiesMisc:aiProviderValidation.apiKeyRequired"),
  }),
  base_url: z.string(),
  models: z.array(z.string()),
  ssl_verify: z.boolean(),
  connect_timeout_s: z.number().positive({
    error: () => i18n.t("entitiesMisc:aiProviderValidation.timeoutPositive"),
  }),
  request_timeout_s: z.number().positive({
    error: () => i18n.t("entitiesMisc:aiProviderValidation.timeoutPositive"),
  }),
});
export type CreateAIProviderInput = z.infer<typeof CreateAIProviderSchema>;

// Тело запроса как его видит сервер: у вида `runner` ключ пустой, зато есть раннер и имя адреса.
export const CreateAIProviderRequestSchema = z.strictObject({
  name: z.string(),
  type: AIProviderTypeSchema,
  api_key: z.string(),
  base_url: z.string(),
  models: z.array(z.string()),
  ssl_verify: z.boolean(),
  connect_timeout_s: z.number(),
  request_timeout_s: z.number(),
  runner_id: z.string().nullable().optional(),
  runner_endpoint: z.string().nullable().optional(),
});
export type CreateAIProviderRequest = z.infer<
  typeof CreateAIProviderRequestSchema
>;

// Edit form: a blank api_key means "keep the stored key" (the backend treats
// blank/omitted as unchanged), so it is not required here.
export const UpdateAIProviderSchema = z.object({
  name: z
    .string()
    .min(1, {
      error: () => i18n.t("entitiesMisc:aiProviderValidation.nameRequired"),
    })
    .optional(),
  type: AIProviderTypeSchema.optional(),
  api_key: z.string().optional(),
  base_url: z.string().optional(),
  models: z.array(z.string()).optional(),
  ssl_verify: z.boolean().optional(),
  connect_timeout_s: z.number().positive().optional(),
  request_timeout_s: z.number().positive().optional(),
  runner_id: z.string().optional(),
  runner_endpoint: z.string().optional(),
});
export type UpdateAIProviderInput = z.infer<typeof UpdateAIProviderSchema>;
