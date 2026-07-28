import { z } from "zod";
import { apiClient, parseResp } from "@shared/api";
import type { UpdateSettingsRequest } from "@shared/api/types";

export const SettingsResponseSchema = z.object({
  theme: z.string(),
  // Optional for resilience against an older backend that predates this field.
  interface_language: z.enum(["ru", "en"]).optional(),
  default_engine: z.string(),
  latex_passes: z.number().int().min(1).max(10),
  // Optional for resilience against an older backend that predates this field.
  max_concurrent_compiles: z.number().int().min(1).max(8).optional(),
  latex_flags: z.string().nullable(),
  compile_image: z.string().nullable(),
  default_ai_provider_id: z.string().nullable(),
  default_ai_model: z.string().nullable(),
  agent_auto_approve_writes: z.boolean(),
  // Optional for resilience against an older backend that predates this field.
  agent_enabled_tools: z.array(z.string()).nullable().optional(),
  // Sticky default agent role new chats inherit. Optional for old backends.
  default_agent_persona: z.string().nullable().optional(),
  default_agent_persona_instructions: z.string().nullable().optional(),
  // Ставить вышедшие обновления самостоятельно. Optional for resilience against
  // an older backend that predates this field.
  auto_update: z.boolean().optional(),
  // Optional for resilience against an older backend that predates this field.
  disk_usage_warn_gb: z.number().int().min(0).max(500).optional(),
});

export type SettingsData = z.infer<typeof SettingsResponseSchema>;

export const settingsApi = {
  get: () => apiClient.get(`/settings`).then(parseResp(SettingsResponseSchema)),

  update: (body: UpdateSettingsRequest) =>
    apiClient.put(`/settings`, body).then(parseResp(SettingsResponseSchema)),
};
