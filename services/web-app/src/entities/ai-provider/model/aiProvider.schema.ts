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
  // Через мой раннер: адреса нет, запросы передаёт личный раннер хозяина
  // на ИИ-адрес, который он сам объявил (Ollama, vLLM, LM Studio в его сети).
  "runner",
]);
export type AIProviderType = z.infer<typeof AIProviderTypeSchema>;

export const AIProviderSourceSchema = z.enum(["own", "org", "instance"]);
export type AIProviderSource = z.infer<typeof AIProviderSourceSchema>;

export const RELAY_STATES = [
  "ready",
  "runner_offline",
  "runner_paused",
  "runner_revoked",
  "endpoint_missing",
  "disabled",
] as const;
export const AiProviderRelaySchema = z.object({
  runner_id: z.string(),
  runner_name: z.string(),
  endpoint: z.string(),
  flavor: z.enum(["openai", "ollama"]),
  state: z.enum(RELAY_STATES),
});
export type AiProviderRelay = z.infer<typeof AiProviderRelaySchema>;
export type RelayState = AiProviderRelay["state"];

// Server response — note there is no `api_key`: the backend exposes only
// `has_api_key` so the secret never reaches the browser.
export const AIProviderSchema = z.object({
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
  // Откуда провайдер: свой, организации или установки (shared == source "instance").
  source: AIProviderSourceSchema.optional(),
  // Провайдер «через мой раннер»: какой раннер и адрес, готов ли он сейчас.
  relay: AiProviderRelaySchema.nullable().optional(),
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
  // Только у вида runner: свой раннер и имя адреса, который он объявил.
  runner_id: z.string().optional(),
  runner_endpoint: z.string().optional(),
});
export type CreateAIProviderInput = z.infer<typeof CreateAIProviderSchema>;

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
