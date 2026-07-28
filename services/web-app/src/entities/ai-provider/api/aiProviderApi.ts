import { z } from "zod";
import { apiClient, parseResp } from "@shared/api";
import {
  AIProviderSchema,
  ProviderModelsSchema,
  type CreateAIProviderInput,
  type UpdateAIProviderInput,
} from "../model/aiProvider.schema";

const AIProviderListSchema = z.array(AIProviderSchema);

export const aiProviderApi = {
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
