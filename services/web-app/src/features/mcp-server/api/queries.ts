import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { mcpApi, type McpScope } from "./mcpApi";
import type { McpSettingsChange } from "./schemas";

export const mcpKeys = {
  info: ["mcp", "info"] as const,
  settings: (scope: McpScope) => ["mcp", scope, "settings"] as const,
  calls: (scope: McpScope) => ["mcp", scope, "calls"] as const,
};

export const CALLS_LIMIT = 50;
const CALLS_POLL_MS = 15000;

export const useMcpInfo = () =>
  useQuery({ queryKey: mcpKeys.info, queryFn: () => mcpApi.info() });

export const useMcpSettings = (scope: McpScope) =>
  useQuery({
    queryKey: mcpKeys.settings(scope),
    queryFn: () => mcpApi.settings(scope),
  });

export const useMcpCalls = (scope: McpScope, enabled: boolean) =>
  useQuery({
    queryKey: mcpKeys.calls(scope),
    queryFn: () => mcpApi.calls(scope, CALLS_LIMIT),
    enabled,
    refetchInterval: CALLS_POLL_MS,
  });

export const useSaveMcpSettings = (scope: McpScope) => {
  const client = useQueryClient();
  return useMutation({
    mutationFn: (body: McpSettingsChange) => mcpApi.save(scope, body),
    onSuccess: (settings) => {
      client.setQueryData(mcpKeys.settings(scope), settings);
      void client.invalidateQueries({ queryKey: mcpKeys.info });
    },
  });
};
