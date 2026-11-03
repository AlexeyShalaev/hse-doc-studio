import { z } from "zod";

export const McpToolGroupSchema = z.enum([
  "account",
  "projects",
  "files",
  "build",
  "checks",
  "review",
  "history",
  "submission",
  "admin",
]);

export const McpToolSchema = z.strictObject({
  name: z.string(),
  group: McpToolGroupSchema,
  kind: z.enum(["read", "write", "exec", "ask"]),
  description: z.string(),
  dangerous: z.boolean(),
  admin: z.boolean(),
  enabled: z.boolean(),
});

export const McpSettingsSchema = z.strictObject({
  enabled: z.boolean(),
  disabled_tools: z.array(z.string()),
  disabled_groups: z.array(McpToolGroupSchema),
  enabled_dangerous: z.array(z.string()),
  endpoint_path: z.string(),
  tools: z.array(McpToolSchema),
});

export const McpCallSchema = z.strictObject({
  at: z.string(),
  tool: z.string(),
  outcome: z.enum(["ok", "error", "denied"]),
  duration_ms: z.number(),
  actor_id: z.string().nullable(),
  actor_name: z.string().nullable(),
  project_id: z.string().nullable(),
  error_code: z.string().nullable(),
  client: z.string().nullable(),
  arg_keys: z.array(z.string()),
});

export const McpInfoSchema = z.strictObject({
  enabled: z.boolean(),
  mode: z.enum(["local", "server"]),
  endpoint_path: z.string(),
  token_scope: z.string().nullable(),
  tools: z.array(z.string()),
});

export type McpToolGroup = z.infer<typeof McpToolGroupSchema>;
export type McpTool = z.infer<typeof McpToolSchema>;
export type McpSettings = z.infer<typeof McpSettingsSchema>;
export type McpCall = z.infer<typeof McpCallSchema>;
export type McpInfo = z.infer<typeof McpInfoSchema>;

/** Тело PUT: null значит «не менять», списки заменяются целиком. */
export type McpSettingsChange = {
  enabled?: boolean;
  disabled_tools?: string[];
  disabled_groups?: McpToolGroup[];
  enabled_dangerous?: string[];
};
