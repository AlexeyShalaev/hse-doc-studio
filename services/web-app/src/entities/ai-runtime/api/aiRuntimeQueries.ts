import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { aiRuntimeApi } from "./aiRuntimeApi";
import type {
  DeleteModelResponse,
  HardwareInfo,
  LoadedModelsResponse,
  ModelCatalog,
  OllamaRuntimeStatus,
  PullJob,
  PullJobsResponse,
  RegistrySearchResponse,
  StartRuntimeResponse,
  StopRuntimeResponse,
  SyncProviderResponse,
  UnloadModelResponse,
} from "../model/aiRuntime.schema";

export const aiRuntimeKeys = {
  all: ["ai-runtime"] as const,
  hardware: () => [...aiRuntimeKeys.all, "hardware"] as const,
  catalog: () => [...aiRuntimeKeys.all, "catalog"] as const,
  status: () => [...aiRuntimeKeys.all, "status"] as const,
  registry: (query: string) =>
    [...aiRuntimeKeys.all, "registry", query] as const,
  pulls: () => [...aiRuntimeKeys.all, "pulls"] as const,
  loaded: () => [...aiRuntimeKeys.all, "loaded"] as const,
};

const LOADED_POLL_MS = 4000;

export const useLoadedModels = () =>
  useQuery<LoadedModelsResponse>({
    queryKey: aiRuntimeKeys.loaded(),
    queryFn: () => aiRuntimeApi.listLoaded(),
    refetchInterval: LOADED_POLL_MS, // reflect Ollama's auto-unload promptly
  });

export const useUnloadModel = () => {
  const queryClient = useQueryClient();
  return useMutation<UnloadModelResponse, Error, string>({
    mutationFn: (name) => aiRuntimeApi.unloadModel(name),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: aiRuntimeKeys.loaded() });
    },
  });
};

const MIN_SEARCH_LEN = 2;
const PULL_POLL_MS = 1000;

export const usePulls = () =>
  useQuery<PullJobsResponse>({
    queryKey: aiRuntimeKeys.pulls(),
    queryFn: () => aiRuntimeApi.listPulls(),
    // Poll while anything is downloading; stop once everything has settled.
    refetchInterval: (query) =>
      (query.state.data?.jobs ?? []).some((j) => j.state === "running")
        ? PULL_POLL_MS
        : false,
  });

export const useStartPull = () => {
  const queryClient = useQueryClient();
  return useMutation<PullJob, Error, string>({
    mutationFn: (name) => aiRuntimeApi.startPull(name),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: aiRuntimeKeys.pulls() });
    },
  });
};

export const useDismissPull = () => {
  const queryClient = useQueryClient();
  return useMutation<string, Error, string>({
    mutationFn: (name) => aiRuntimeApi.dismissPull(name),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: aiRuntimeKeys.pulls() });
    },
  });
};

export const useSyncProvider = () =>
  useMutation<SyncProviderResponse>({
    mutationFn: () => aiRuntimeApi.syncProvider(),
  });

export const useSearchRegistry = (query: string) =>
  useQuery<RegistrySearchResponse>({
    queryKey: aiRuntimeKeys.registry(query),
    queryFn: () => aiRuntimeApi.searchRegistry(query),
    enabled: query.trim().length >= MIN_SEARCH_LEN,
    staleTime: 5 * 60_000,
    placeholderData: (prev) => prev, // keep prior results visible while typing
  });

export const useHardwareInfo = () =>
  useQuery<HardwareInfo>({
    queryKey: aiRuntimeKeys.hardware(),
    queryFn: () => aiRuntimeApi.hardware(),
    staleTime: 5 * 60_000, // hardware doesn't change within a session
  });

export const useModelCatalog = () =>
  useQuery<ModelCatalog>({
    queryKey: aiRuntimeKeys.catalog(),
    queryFn: () => aiRuntimeApi.catalog(),
    staleTime: 5 * 60_000,
  });

export const useOllamaRuntimeStatus = () =>
  useQuery<OllamaRuntimeStatus>({
    queryKey: aiRuntimeKeys.status(),
    queryFn: () => aiRuntimeApi.status(),
    staleTime: 3_000,
  });

// Refreshes only runtime-owned queries. The managed `ollama` provider lives in
// a different entity, so refreshing the provider list (which the backend syncs
// on start/pull/delete) is the feature layer's job — see manage-local-runtime.
export const useInvalidateRuntime = () => {
  const queryClient = useQueryClient();
  return () => {
    void queryClient.invalidateQueries({ queryKey: aiRuntimeKeys.status() });
    void queryClient.invalidateQueries({ queryKey: aiRuntimeKeys.catalog() });
  };
};

export const useStartRuntime = () => {
  const invalidate = useInvalidateRuntime();
  return useMutation<StartRuntimeResponse>({
    mutationFn: () => aiRuntimeApi.start(),
    onSuccess: invalidate,
  });
};

export const useStopRuntime = () => {
  const invalidate = useInvalidateRuntime();
  return useMutation<StopRuntimeResponse>({
    mutationFn: () => aiRuntimeApi.stop(),
    onSuccess: invalidate,
  });
};

export const useDeleteModel = () => {
  const invalidate = useInvalidateRuntime();
  return useMutation<DeleteModelResponse, Error, string>({
    mutationFn: (name) => aiRuntimeApi.deleteModel(name),
    onSuccess: invalidate,
  });
};
