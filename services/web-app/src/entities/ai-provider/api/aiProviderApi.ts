import { z } from "zod";
import { adminClient, apiClient, parseResp } from "@shared/api";
import {
  AIProviderSchema,
  ProviderModelsSchema,
  type CreateAIProviderInput,
  type UpdateAIProviderInput,
} from "../model/aiProvider.schema";

const AIProviderListSchema = z.array(AIProviderSchema);

/** Чей это провайдер: личный (по умолчанию) или общий провайдер установки (админка). */
export type AIProviderOwner = "user" | "instance";

export const aiProviderApiFor = (owner: AIProviderOwner = "user") => {
  const client = owner === "instance" ? adminClient : apiClient;
  // У общих провайдеров отказ показывает сама страница админки, а не общий тост.
  const quiet = owner === "instance" ? { silentError: true } : undefined;
  return {
    list: () =>
      client.get(`/ai-providers`).then(parseResp(AIProviderListSchema)),

    create: (body: CreateAIProviderInput) =>
      client.post(`/ai-providers`, body).then(parseResp(AIProviderSchema)),

    update: (id: string, body: UpdateAIProviderInput) =>
      client
        .patch(`/ai-providers/${id}`, body)
        .then(parseResp(AIProviderSchema)),

    remove: (id: string) =>
      client.delete(`/ai-providers/${id}`, quiet).then(() => id),

    // Live model listing — doubles as a connection/credentials check.
    fetchModels: (id: string) =>
      client
        .get(`/ai-providers/${id}/models`)
        .then(parseResp(ProviderModelsSchema)),
  };
};

export const aiProviderApi = aiProviderApiFor("user");
