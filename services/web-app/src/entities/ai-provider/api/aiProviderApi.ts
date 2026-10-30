import { z } from "zod";
import { adminClient, apiClient, parseResp } from "@shared/api";
import {
  AIProviderSchema,
  ProviderModelsSchema,
  type CreateAIProviderInput,
  type UpdateAIProviderInput,
} from "../model/aiProvider.schema";

const AIProviderListSchema = z.array(AIProviderSchema);

// Общие провайдеры установки админка отдаёт в своей форме (api/schemas/admin_ops.py): ключ там
// только признак `key_set`, правка принимает все поля сразу, а проверка подключения идёт отдельным запросом.
const InstanceProviderSchema = z.object({
  id: z.string(),
  name: z.string(),
  type: AIProviderSchema.shape.type,
  base_url: z.string(),
  models: z.array(z.string()),
  key_set: z.boolean(),
  ssl_verify: z.boolean(),
  connect_timeout_s: z.number(),
  request_timeout_s: z.number(),
  created_at: z.string(),
});
const InstanceCheckSchema = z.object({
  ok: z.boolean(),
  models: z.array(z.string()),
  error: z.string().nullable(),
});

const fromInstance = (wire: z.infer<typeof InstanceProviderSchema>) =>
  AIProviderSchema.parse({
    ...wire,
    has_api_key: wire.key_set,
    shared: true,
  });

const toInstanceUpdate = (body: UpdateAIProviderInput) => ({
  name: null,
  type: null,
  api_key: null,
  clear_key: false,
  base_url: null,
  models: null,
  ssl_verify: null,
  connect_timeout_s: null,
  request_timeout_s: null,
  ...body,
});

/** Чей это провайдер: личный (по умолчанию) или общий провайдер установки (админка). */
export type AIProviderOwner = "user" | "instance";

export const aiProviderApiFor = (owner: AIProviderOwner = "user") => {
  if (owner === "instance") return instanceApi;
  return {
    list: () =>
      apiClient.get(`/ai-providers`).then(parseResp(AIProviderListSchema)),

    create: (body: CreateAIProviderInput) =>
      apiClient.post(`/ai-providers`, body).then(parseResp(AIProviderSchema)),

    update: (id: string, body: UpdateAIProviderInput) =>
      apiClient
        .patch(`/ai-providers/${id}`, body)
        .then(parseResp(AIProviderSchema)),

    remove: (id: string) =>
      apiClient.delete(`/ai-providers/${id}`).then(() => id),

    // Live model listing — doubles as a connection/credentials check.
    fetchModels: (id: string) =>
      apiClient
        .get(`/ai-providers/${id}/models`)
        .then(parseResp(ProviderModelsSchema)),
  };
};

// У общих провайдеров отказ показывает сама страница админки, а не общий тост.
const quiet = { silentError: true } as const;

const instanceApi = {
  list: () =>
    adminClient
      .get(`/ai-providers`, { ...quiet, params: { limit: 200 } })
      .then(parseResp(z.object({ items: z.array(InstanceProviderSchema) })))
      .then((page) => page.items.map(fromInstance)),

  create: (body: CreateAIProviderInput) =>
    adminClient
      .post(`/ai-providers`, body)
      .then(parseResp(InstanceProviderSchema))
      .then(fromInstance),

  update: (id: string, body: UpdateAIProviderInput) =>
    adminClient
      .patch(`/ai-providers/${id}`, toInstanceUpdate(body))
      .then(parseResp(InstanceProviderSchema))
      .then(fromInstance),

  remove: (id: string) =>
    adminClient.delete(`/ai-providers/${id}`, quiet).then(() => id),

  // Проверка подключения: сбой провайдера приходит ответом ok=false, а не ошибкой запроса.
  fetchModels: async (id: string) => {
    const check = await adminClient
      .post(`/ai-providers/${id}/check`, {})
      .then(parseResp(InstanceCheckSchema));
    if (!check.ok) throw new Error(check.error ?? "provider_unavailable");
    return { models: check.models };
  },
};

export const aiProviderApi = aiProviderApiFor("user");
