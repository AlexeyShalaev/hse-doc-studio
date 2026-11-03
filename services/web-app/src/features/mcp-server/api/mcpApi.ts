import type { AxiosInstance } from "axios";
import { adminClient, apiClient, parseResp } from "@shared/api";
import {
  McpCallSchema,
  McpInfoSchema,
  McpSettingsSchema,
  type McpCall,
  type McpInfo,
  type McpSettings,
  type McpSettingsChange,
} from "./schemas";

/** Где лежат настройки: админка облака или локальная Студия (те же пути). */
export type McpScope = "admin" | "local";

const quiet = { silentError: true } as const;

const clientOf = (scope: McpScope): AxiosInstance =>
  scope === "admin" ? adminClient : apiClient;

export const mcpApi = {
  info: (): Promise<McpInfo> =>
    apiClient.get("/mcp/info", quiet).then(parseResp(McpInfoSchema)),
  settings: (scope: McpScope): Promise<McpSettings> =>
    clientOf(scope)
      .get("/mcp/settings", quiet)
      .then(parseResp(McpSettingsSchema)),
  save: (scope: McpScope, body: McpSettingsChange): Promise<McpSettings> =>
    clientOf(scope)
      .put("/mcp/settings", body, quiet)
      .then(parseResp(McpSettingsSchema)),
  calls: (scope: McpScope, limit: number): Promise<McpCall[]> =>
    clientOf(scope)
      .get("/mcp/calls", { ...quiet, params: { limit } })
      .then(parseResp(McpCallSchema.array())),
};
