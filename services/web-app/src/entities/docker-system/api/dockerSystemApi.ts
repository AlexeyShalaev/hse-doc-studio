import { z } from "zod";
import { apiClient, parseResp } from "@shared/api";

export const DockerImageUsageSchema = z.object({
  reference: z.string(),
  repository: z.string(),
  tag: z.string(),
  size_bytes: z.number().int().nonnegative(),
  created: z.string(),
  in_use: z.boolean(),
  category: z.string(),
  dangling: z.boolean(),
  protected: z.boolean(),
});

export type DockerImageUsage = z.infer<typeof DockerImageUsageSchema>;

export const DockerContainerUsageSchema = z.object({
  name: z.string(),
  image: z.string(),
  state: z.string(),
  status: z.string(),
  size_bytes: z.number().int().nonnegative(),
  managed: z.boolean(),
});

export type DockerContainerUsage = z.infer<typeof DockerContainerUsageSchema>;

export const DockerVolumeUsageSchema = z.object({
  name: z.string(),
  size_bytes: z.number().int().nonnegative(),
  links: z.number().int().nonnegative(),
  managed: z.boolean(),
});

export type DockerVolumeUsage = z.infer<typeof DockerVolumeUsageSchema>;

export const DockerUsageSchema = z.object({
  available: z.boolean(),
  images: z.array(DockerImageUsageSchema),
  containers: z.array(DockerContainerUsageSchema),
  volumes: z.array(DockerVolumeUsageSchema),
  images_total_bytes: z.number().int().nonnegative(),
  containers_total_bytes: z.number().int().nonnegative(),
  volumes_total_bytes: z.number().int().nonnegative(),
  build_cache_bytes: z.number().int().nonnegative(),
  build_cache_reclaimable_bytes: z.number().int().nonnegative(),
  build_cache_count: z.number().int().nonnegative(),
  total_bytes: z.number().int().nonnegative(),
  cleanable_bytes: z.number().int().nonnegative(),
});

export type DockerUsage = z.infer<typeof DockerUsageSchema>;

export const CLEANUP_TARGETS = [
  "build_cache",
  "dangling_images",
  "unused_images",
  "stopped_containers",
] as const;

export type CleanupTarget = (typeof CLEANUP_TARGETS)[number];

export const CleanupStepSchema = z.object({
  kind: z.enum(["build_cache", "dangling_images", "image", "container"]),
  ref: z.string().nullable(),
  status: z.enum(["pending", "running", "done", "error", "skipped"]),
  freed_bytes: z.number().int().nonnegative(),
  error: z.string().nullable(),
});

export type CleanupStep = z.infer<typeof CleanupStepSchema>;

export const CleanupJobSchema = z.object({
  id: z.string(),
  status: z.enum(["running", "cancelling", "done", "cancelled", "error"]),
  steps: z.array(CleanupStepSchema),
  freed_bytes: z.number().int().nonnegative(),
});

export type CleanupJob = z.infer<typeof CleanupJobSchema>;

export const CleanupJobStateSchema = z.object({
  job: CleanupJobSchema.nullable(),
});

export type CleanupJobState = z.infer<typeof CleanupJobStateSchema>;

export const isJobActive = (job: CleanupJob | null | undefined): boolean =>
  job?.status === "running" || job?.status === "cancelling";

export type DockerCleanupInput = {
  targets?: CleanupTarget[];
  images?: string[];
  containers?: string[];
};

export const dockerSystemApi = {
  usage: () =>
    apiClient.get("/system/docker-usage").then(parseResp(DockerUsageSchema)),

  startCleanup: (body: DockerCleanupInput) =>
    apiClient
      .post("/system/docker-cleanup", {
        targets: body.targets ?? [],
        images: body.images ?? [],
        containers: body.containers ?? [],
      })
      .then(parseResp(CleanupJobSchema)),

  cleanupJob: () =>
    apiClient
      .get("/system/docker-cleanup")
      .then(parseResp(CleanupJobStateSchema)),

  cancelCleanup: () =>
    apiClient
      .post("/system/docker-cleanup/cancel")
      .then(parseResp(CleanupJobStateSchema)),
};
