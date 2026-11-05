import { z } from "zod";

// Контракт статуса сборок (docs/design/connected-devices.md, часть 3).

export const BuildSchema = z.strictObject({
  at: z.string(),
  commit: z.string().nullable(),
  pages: z.number().int().nullable(),
  // true: собран из текущей версии проекта; false: версия изменилась; null: коммит неизвестен.
  fresh: z.boolean().nullable(),
  sha256: z.string().nullable(),
  size: z.number().int().nullable(),
  // Идентификатор облачной сборки; у выгрузки Студии его нет.
  compile_id: z.string().nullable().optional(),
});
export type Build = z.infer<typeof BuildSchema>;

export const StudioBuildSchema = BuildSchema.extend({
  artifact_id: z.string(),
  by_name: z.string().nullable(),
});
export type StudioBuild = z.infer<typeof StudioBuildSchema>;

export const DocumentBuildsSchema = z.strictObject({
  doc_id: z.string(),
  cloud: BuildSchema.nullable(),
  cloud_running: z.boolean(),
  cloud_failed_at: z.string().nullable(),
  studio: StudioBuildSchema.nullable(),
});
export type DocumentBuilds = z.infer<typeof DocumentBuildsSchema>;

/** Облако: `GET /api/v1/projects/{id}/builds`. */
export const ProjectBuildsSchema = z.strictObject({
  head: z.string().nullable(),
  dirty: z.boolean(),
  documents: z.array(DocumentBuildsSchema),
  max_pdf_bytes: z.number().int(),
});
export type ProjectBuilds = z.infer<typeof ProjectBuildsSchema>;

export const BUILD_RELATIONS = [
  "none",
  "cloud_only",
  "local_only",
  "same",
  "cloud_newer",
  "local_newer",
] as const;
export type BuildRelation = (typeof BUILD_RELATIONS)[number];

export const LocalBuildSchema = z.strictObject({
  at: z.string(),
  commit: z.string().nullable(),
  fresh: z.boolean().nullable(),
  sha256: z.string().nullable(),
  pages: z.number().int().nullable(),
  from_cloud: z.boolean(),
});
export type LocalBuild = z.infer<typeof LocalBuildSchema>;

export const DocumentBuildStatusSchema = z.strictObject({
  doc_id: z.string(),
  local: LocalBuildSchema.nullable(),
  cloud: BuildSchema.nullable(),
  cloud_running: z.boolean(),
  studio: BuildSchema.nullable(),
  relation: z.enum(BUILD_RELATIONS),
  can_fetch: z.boolean(),
});
export type DocumentBuildStatus = z.infer<typeof DocumentBuildStatusSchema>;

/** Локальная Студия: `GET /api/v1/projects/{id}/git/builds`. */
export const LocalBuildsSchema = z.strictObject({
  connected: z.boolean(),
  cloud_error: z.string().nullable(),
  local_head: z.string().nullable(),
  local_dirty: z.boolean(),
  cloud_head: z.string().nullable(),
  documents: z.array(DocumentBuildStatusSchema),
});
export type LocalBuilds = z.infer<typeof LocalBuildsSchema>;

export const FETCH_STATUSES = [
  "downloaded",
  "unchanged",
  "kept_local",
  "skipped_stale",
  "too_large",
  "no_cloud_build",
  "failed",
] as const;
export type FetchStatus = (typeof FETCH_STATUSES)[number];

export const FetchBuildRequestSchema = z.strictObject({
  doc_id: z.string().nullable().optional(),
  force: z.boolean().optional(),
  auto: z.boolean().optional(),
});
export type FetchBuildRequest = z.infer<typeof FetchBuildRequestSchema>;

export const FetchBuildResponseSchema = z.strictObject({
  items: z.array(
    z.strictObject({
      doc_id: z.string(),
      status: z.enum(FETCH_STATUSES),
      code: z.string().nullable(),
      size: z.number().int().nullable(),
    }),
  ),
});
export type FetchBuildResponse = z.infer<typeof FetchBuildResponseSchema>;

/** Остановка облачных сборок из локальной Студии: `POST /api/v1/projects/{id}/git/builds/cancel`. */
export const CancelCloudBuildsResponseSchema = z.strictObject({
  cancelled: z.number().int().min(0),
});
export type CancelCloudBuildsResponse = z.infer<
  typeof CancelCloudBuildsResponseSchema
>;
