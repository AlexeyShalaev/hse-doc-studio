import { z } from "zod";
import { i18n } from "@shared/lib";

// A user-defined custom agent role (mirrors api/schemas/agent_personas.py).
export const AgentPersonaSchema = z.object({
  id: z.string(),
  label: z.string(),
  description: z.string(),
  instruction: z.string(),
  created_at: z.string(),
});
export type AgentPersona = z.infer<typeof AgentPersonaSchema>;
export const AgentPersonaListSchema = z.array(AgentPersonaSchema);

// A shipped preset role — read-only, exposed with its instruction so the
// Settings UI can show it and duplicate it into an editable custom role.
export const BuiltinPersonaSchema = z.object({
  id: z.string(),
  label: z.string(),
  description: z.string(),
  instruction: z.string(),
});
export type BuiltinPersona = z.infer<typeof BuiltinPersonaSchema>;
export const BuiltinPersonaListSchema = z.array(BuiltinPersonaSchema);

export const CreateAgentPersonaSchema = z.object({
  label: z.string().min(1, {
    error: () => i18n.t("entitiesMisc:agentPersonaValidation.labelRequired"),
  }),
  instruction: z.string().min(1, {
    error: () =>
      i18n.t("entitiesMisc:agentPersonaValidation.instructionRequired"),
  }),
  description: z.string(),
});
export type CreateAgentPersonaInput = z.infer<typeof CreateAgentPersonaSchema>;

export const UpdateAgentPersonaSchema = z.object({
  label: z.string().min(1).optional(),
  description: z.string().optional(),
  instruction: z.string().min(1).optional(),
});
export type UpdateAgentPersonaInput = z.infer<typeof UpdateAgentPersonaSchema>;
