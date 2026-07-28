import { apiClient, parseResp } from "@shared/api";
import { env } from "@shared/config";
import {
  DeleteModelResponseSchema,
  HardwareInfoSchema,
  LoadedModelsResponseSchema,
  ModelCatalogSchema,
  OllamaRuntimeStatusSchema,
  PullJobSchema,
  PullJobsResponseSchema,
  RegistrySearchResponseSchema,
  StartRuntimeResponseSchema,
  StopRuntimeResponseSchema,
  SyncProviderResponseSchema,
  UnloadModelResponseSchema,
} from "../model/aiRuntime.schema";

const apiBase = `${env.VITE_API_BASE_URL}/api/v1`;

export const aiRuntimeApi = {
  hardware: () =>
    apiClient.get(`/ai-runtime/hardware`).then(parseResp(HardwareInfoSchema)),

  catalog: () =>
    apiClient.get(`/ai-runtime/catalog`).then(parseResp(ModelCatalogSchema)),

  status: () =>
    apiClient
      .get(`/ai-runtime/status`)
      .then(parseResp(OllamaRuntimeStatusSchema)),

  start: () =>
    apiClient
      .post(`/ai-runtime/start`)
      .then(parseResp(StartRuntimeResponseSchema)),

  stop: () =>
    apiClient
      .post(`/ai-runtime/stop`)
      .then(parseResp(StopRuntimeResponseSchema)),

  deleteModel: (name: string) =>
    apiClient
      .delete(`/ai-runtime/models`, { params: { name } })
      .then(parseResp(DeleteModelResponseSchema)),

  searchRegistry: (q: string) =>
    apiClient
      .get(`/ai-runtime/registry/search`, { params: { q } })
      .then(parseResp(RegistrySearchResponseSchema)),

  // Background model downloads (run server-side, independent of the UI).
  startPull: (name: string) =>
    apiClient
      .post(`/ai-runtime/models/pull`, undefined, { params: { name } })
      .then(parseResp(PullJobSchema)),

  listPulls: () =>
    apiClient
      .get(`/ai-runtime/models/pulls`)
      .then(parseResp(PullJobsResponseSchema)),

  dismissPull: (name: string) =>
    apiClient
      .delete(`/ai-runtime/models/pulls`, { params: { name } })
      .then(() => name),

  syncProvider: () =>
    apiClient
      .post(`/ai-runtime/provider/sync`)
      .then(parseResp(SyncProviderResponseSchema)),

  // Models currently held in memory (and freeing them on demand).
  listLoaded: () =>
    apiClient
      .get(`/ai-runtime/models/loaded`)
      .then(parseResp(LoadedModelsResponseSchema)),

  unloadModel: (name: string) =>
    apiClient
      .post(`/ai-runtime/models/unload`, undefined, { params: { name } })
      .then(parseResp(UnloadModelResponseSchema)),

  // SSE endpoint (engine image install is still streamed live; it's a one-off).
  installEngineStreamUrl: () => `${apiBase}/ai-runtime/engine/install`,
};
