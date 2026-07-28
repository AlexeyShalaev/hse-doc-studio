import { z } from "zod";

// Mirrors the backend api/schemas/chat.py. Agent run events stream over SSE and
// are typed separately in the feature layer (useAgentRunStream).

export const TokenUsageSchema = z.object({
  input_tokens: z.number(),
  output_tokens: z.number(),
  total_tokens: z.number(),
});
export type TokenUsage = z.infer<typeof TokenUsageSchema>;

export const ChatContentBlockSchema = z.object({
  kind: z.enum(["text", "tool_call", "tool_result"]),
  text: z.string().nullable().optional(),
  call_id: z.string().nullable().optional(),
  tool_name: z.string().nullable().optional(),
  args: z.record(z.string(), z.unknown()).default({}),
  result: z.string().nullable().optional(),
  is_error: z.boolean().default(false),
});
export type ChatContentBlock = z.infer<typeof ChatContentBlockSchema>;

export const ChatMessageSchema = z.object({
  id: z.string(),
  seq: z.number(),
  role: z.enum(["system", "user", "assistant", "tool", "summary"]),
  blocks: z.array(ChatContentBlockSchema),
  created_at: z.string(),
  model: z.string().nullable().optional(),
  provider_id: z.string().nullable().optional(),
  usage: TokenUsageSchema.nullable().optional(),
  approval: z.string(),
});
export type ChatMessage = z.infer<typeof ChatMessageSchema>;

export const ChatSessionSchema = z.object({
  id: z.string(),
  title: z.string(),
  doc_id: z.string().nullable(),
  // Project this chat is bound to (null = global/system chat).
  project_id: z.string().nullable().default(null),
  created_at: z.string(),
  updated_at: z.string(),
  archived: z.boolean(),
  message_count: z.number(),
  last_run_id: z.string().nullable(),
  default_provider_id: z.string().nullable(),
  default_model: z.string().nullable(),
  // The agent role for this chat: a persona id (or null) + free-form text
  // when persona === "custom".
  persona: z.string().nullable().default(null),
  persona_instructions: z.string().nullable().default(null),
  is_running: z.boolean().default(false),
});
export type ChatSession = z.infer<typeof ChatSessionSchema>;

export const ChatSessionDetailSchema = ChatSessionSchema.extend({
  messages: z.array(ChatMessageSchema),
  active_run_id: z.string().nullable(),
});
export type ChatSessionDetail = z.infer<typeof ChatSessionDetailSchema>;

export const StartTurnResponseSchema = z.object({
  run_id: z.string(),
  user_message_seq: z.number(),
});
export type StartTurnResponse = z.infer<typeof StartTurnResponseSchema>;

export const CancelTurnResponseSchema = z.object({
  cancelled_task: z.boolean(),
  record_finalized: z.boolean(),
});
export type CancelTurnResponse = z.infer<typeof CancelTurnResponseSchema>;

// The agent's tool catalog (for the Configure-Tools UI). Mirrors
// api/schemas/chat.py AgentToolResponse.
export const AgentToolSchema = z.object({
  name: z.string(),
  description: z.string(),
  kind: z.string(), // read | write | exec
  // False = an app/system tool that works without a project; the unified agent
  // hides project-only tools when the chat isn't bound to a project.
  requires_project: z.boolean().default(true),
});
export type AgentTool = z.infer<typeof AgentToolSchema>;

// A selectable agent role. Mirrors api/schemas/chat.py PersonaResponse.
export const PersonaSchema = z.object({
  id: z.string(),
  label: z.string(),
  description: z.string(),
  // False = a user-defined custom role (vs. a shipped built-in).
  builtin: z.boolean().default(true),
});
export type Persona = z.infer<typeof PersonaSchema>;
export const PersonaListSchema = z.array(PersonaSchema);

export type CreateChatSessionInput = {
  title?: string;
  doc_id?: string;
  provider_id?: string;
  model?: string;
  // Unified agent: bind a new chat to a project (project tools + context).
  project_id?: string;
  // Agent role + free-form text (when persona === "custom").
  persona?: string;
  persona_instructions?: string;
};

// Partial session update (PATCH): only the provided fields change. A null
// persona_instructions clears stale custom text when switching to a preset.
export type UpdateChatSessionInput = {
  title?: string;
  persona?: string;
  persona_instructions?: string | null;
};

export type StartTurnInput = {
  text: string;
  provider_id?: string;
  model?: string;
};
