import { z } from "zod";

export const EngineSchema = z.enum(["ollama", "vllm", "sglang"]);
export type Engine = z.infer<typeof EngineSchema>;

export const HardwareSchema = z.object({
  gpu_vendor: z.enum(["nvidia", "amd", "apple", "none"]),
  gpu_name: z.string().nullable(),
  vram_mb: z.number().nullable(),
  total_ram_mb: z.number().nullable(),
  cpu_count: z.number().nullable(),
  docker_gpu_supported: z.boolean(),
  arch: z.string().nullable(),
  disk_free_mb: z.number().nullable(),
});

export const CapabilitiesSchema = z.object({
  local_enabled: z.boolean(),
  docker_available: z.boolean(),
  hardware: HardwareSchema,
  engines: z.array(
    z.object({
      engine: EngineSchema,
      image: z.string(),
      available: z.boolean(),
      reasons: z.array(z.string()),
    }),
  ),
});
export type Capabilities = z.infer<typeof CapabilitiesSchema>;

export const CatalogSchema = z.object({
  items: z.array(
    z.object({
      ref: z.string(),
      title: z.string(),
      params_b: z.number(),
      quant: z.string(),
    }),
  ),
});
export type CatalogModel = z.infer<typeof CatalogSchema>["items"][number];

export const EstimateSchema = z.object({
  fit: z.enum(["fits", "tight", "too_large", "unknown"]),
  params_b: z.number().nullable(),
  weights_mb: z.number().nullable(),
  needed_mb: z.number().nullable(),
  available_mb: z.number().nullable(),
  memory_kind: z.enum(["vram", "ram"]),
  disk_ok: z.boolean().nullable(),
  reasons: z.array(z.string()),
});
export type Estimate = z.infer<typeof EstimateSchema>;

export const StepStateSchema = z.enum(["pending", "running", "done", "failed"]);
export type StepState = z.infer<typeof StepStateSchema>;

export const ModelServerSchema = z.object({
  id: z.string(),
  engine: EngineSchema,
  model: z.string(),
  name: z.string(),
  status: z.enum(["installing", "running", "stopped", "failed"]),
  endpoint: z.string().nullable(),
  provider_id: z.string().nullable(),
  image: z.string(),
  steps: z.record(z.string(), StepStateSchema),
  percent: z.number().nullable(),
  text: z.string(),
  error: z.string().nullable(),
});
export type ModelServer = z.infer<typeof ModelServerSchema>;

export const ModelServerListSchema = z.object({
  items: z.array(ModelServerSchema),
});

export const LogsSchema = z.object({ text: z.string() });

export type InstallRequest = {
  engine: Engine;
  model: string;
  name?: string;
  force?: boolean;
};
