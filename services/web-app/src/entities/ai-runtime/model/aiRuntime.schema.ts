import { z } from "zod";

export const HardwareInfoSchema = z.object({
  gpu_vendor: z.string(), // nvidia | apple | amd | none
  gpu_name: z.string().nullable(),
  vram_mb: z.number().int().nullable(),
  total_ram_mb: z.number().int().nullable(),
  cpu_count: z.number().int().nullable(),
  docker_gpu_supported: z.boolean(),
});
export type HardwareInfo = z.infer<typeof HardwareInfoSchema>;

export const CatalogModelSchema = z.object({
  name: z.string(),
  label: z.string(),
  family: z.string().default(""),
  params_b: z.number(),
  size_gb: z.number(),
  min_vram_gb: z.number(),
  min_ram_gb: z.number(),
  tasks: z.array(z.string()),
  description: z.string(),
  runnable: z.boolean(),
  on_gpu: z.boolean(),
  recommended: z.boolean(),
  note: z.string(),
});
export type CatalogModel = z.infer<typeof CatalogModelSchema>;

export const ModelCatalogSchema = z.object({
  hardware: HardwareInfoSchema,
  models: z.array(CatalogModelSchema),
  allow_custom: z.boolean(),
});
export type ModelCatalog = z.infer<typeof ModelCatalogSchema>;

export const RegistryModelSchema = z.object({
  name: z.string(),
  description: z.string(),
  pulls: z.string(),
  capabilities: z.array(z.string()),
});
export type RegistryModel = z.infer<typeof RegistryModelSchema>;

export const RegistrySearchResponseSchema = z.object({
  models: z.array(RegistryModelSchema),
});
export type RegistrySearchResponse = z.infer<
  typeof RegistrySearchResponseSchema
>;

export const OllamaRuntimeModeSchema = z.enum(["native", "docker", "none"]);
export type OllamaRuntimeMode = z.infer<typeof OllamaRuntimeModeSchema>;

export const OllamaRuntimeStatusSchema = z.object({
  mode: OllamaRuntimeModeSchema,
  base_url: z.string().nullable(),
  version: z.string().nullable(),
  docker_available: z.boolean(),
  engine_image_installed: z.boolean(),
  installed_models: z.array(z.string()),
});
export type OllamaRuntimeStatus = z.infer<typeof OllamaRuntimeStatusSchema>;

export const StartRuntimeResponseSchema = z.object({
  started: z.boolean(),
  status: OllamaRuntimeStatusSchema,
});
export type StartRuntimeResponse = z.infer<typeof StartRuntimeResponseSchema>;

export const StopRuntimeResponseSchema = z.object({
  stopped: z.boolean(),
  detail: z.string().nullable(),
  status: OllamaRuntimeStatusSchema,
});
export type StopRuntimeResponse = z.infer<typeof StopRuntimeResponseSchema>;

export const DeleteModelResponseSchema = z.object({
  deleted: z.boolean(),
  installed_models: z.array(z.string()),
});
export type DeleteModelResponse = z.infer<typeof DeleteModelResponseSchema>;

export const PullJobStateSchema = z.enum(["running", "success", "failure"]);
export type PullJobState = z.infer<typeof PullJobStateSchema>;

export const PullJobSchema = z.object({
  name: z.string(),
  state: PullJobStateSchema,
  message: z.string(),
  error: z.string().nullable(),
});
export type PullJob = z.infer<typeof PullJobSchema>;

export const PullJobsResponseSchema = z.object({
  jobs: z.array(PullJobSchema),
});
export type PullJobsResponse = z.infer<typeof PullJobsResponseSchema>;

export const SyncProviderResponseSchema = z.object({
  provider_id: z.string().nullable(),
  models: z.array(z.string()),
});
export type SyncProviderResponse = z.infer<typeof SyncProviderResponseSchema>;

export const LoadedModelSchema = z.object({
  name: z.string(),
  size_bytes: z.number().int(),
  vram_bytes: z.number().int(),
  expires_at: z.string().nullable(),
});
export type LoadedModel = z.infer<typeof LoadedModelSchema>;

export const LoadedModelsResponseSchema = z.object({
  models: z.array(LoadedModelSchema),
});
export type LoadedModelsResponse = z.infer<typeof LoadedModelsResponseSchema>;

export const UnloadModelResponseSchema = z.object({
  unloaded: z.boolean(),
});
export type UnloadModelResponse = z.infer<typeof UnloadModelResponseSchema>;
