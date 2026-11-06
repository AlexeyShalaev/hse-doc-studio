import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { modelServersApi } from "./modelServersApi";
import type { Engine, InstallRequest, ModelServer } from "./schemas";

export const modelServerKeys = {
  all: ["admin", "model-servers"] as const,
  capabilities: ["admin", "model-servers", "capabilities"] as const,
  list: ["admin", "model-servers", "list"] as const,
  logs: (id: string) => ["admin", "model-servers", "logs", id] as const,
};

export const useCapabilities = () =>
  useQuery({
    queryKey: modelServerKeys.capabilities,
    queryFn: () => modelServersApi.capabilities(),
    staleTime: 60_000,
  });

const busy = (servers: ModelServer[] | undefined): boolean =>
  servers?.some((s) => s.status === "installing") ?? false;

/** Пока идёт установка, список опрашивается раз в 2 секунды, иначе раз в 15. */
export const useModelServers = () =>
  useQuery({
    queryKey: modelServerKeys.list,
    queryFn: () => modelServersApi.list(),
    staleTime: 0,
    refetchInterval: (query) => (busy(query.state.data) ? 2000 : 15_000),
  });

export const useCatalog = (engine: Engine, q: string) =>
  useQuery({
    queryKey: ["admin", "model-servers", "catalog", engine, q] as const,
    queryFn: () => modelServersApi.catalog(engine, q),
    staleTime: 5 * 60_000,
  });

export const useEstimate = (engine: Engine, model: string) =>
  useQuery({
    queryKey: ["admin", "model-servers", "estimate", engine, model] as const,
    queryFn: () => modelServersApi.estimate(engine, model),
    enabled: model.trim().length > 0,
    staleTime: 60_000,
    retry: false,
  });

export const useServerLogs = (id: string, enabled: boolean) =>
  useQuery({
    queryKey: modelServerKeys.logs(id),
    queryFn: () => modelServersApi.logs(id),
    enabled,
    refetchInterval: enabled ? 3000 : false,
  });

const useRefresh = () => {
  const client = useQueryClient();
  return () => client.invalidateQueries({ queryKey: modelServerKeys.list });
};

export const useInstall = () => {
  const refresh = useRefresh();
  return useMutation({
    mutationFn: (body: InstallRequest) => modelServersApi.install(body),
    onSuccess: refresh,
  });
};

export const useServerAction = () => {
  const refresh = useRefresh();
  return useMutation({
    mutationFn: ({
      id,
      action,
      purge = false,
    }: {
      id: string;
      action: "start" | "stop" | "remove";
      purge?: boolean;
    }): Promise<void> => {
      if (action === "remove") return modelServersApi.remove(id, purge);
      const run =
        action === "start" ? modelServersApi.start : modelServersApi.stop;
      return run(id).then(() => undefined);
    },
    onSuccess: refresh,
  });
};
