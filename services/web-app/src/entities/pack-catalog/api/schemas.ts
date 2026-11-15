import { z } from "zod";

// Контракт «Каталогов паков» (contracts/pack-catalog, срез T17). Эталонные JSON разбирают
// и эти схемы (contract.test.ts), и строгие модели бэкенда
// (services/api/hse_doc_studio/api/schemas/pack_catalog.py).

const LocalizedSchema = z.record(z.string(), z.string());

export const SourceKindSchema = z.enum(["git", "archive", "folder"]);
export const SourceAccessSchema = z.enum(["none", "personal", "service"]);
export const VerdictSchema = z.enum([
  "new",
  "present",
  "changed",
  "incompatible",
  "invalid",
  "unreleased",
]);
export const ConflictSchema = z.enum(["builtin", "other_source", "invalid"]);
export const BlockerSchema = z.enum([
  "pack_conflict",
  "version_changed",
  "version_invalid",
  "no_packs",
]);
export const EventActionSchema = z.enum([
  "add",
  "update",
  "check",
  "apply",
  "enable",
  "disable",
  "remove",
  "track",
]);
export const CatalogOriginSchema = z.enum(["builtin", "subscribed"]);

export const CatalogSourceErrorSchema = z.strictObject({
  code: z.string(),
  detail: z.string(),
});

export const CatalogVersionSchema = z.strictObject({
  template: z.string(),
  version: z.string(),
  // false: версия есть для существующих проектов, но мастер её не предлагает.
  listed: z.boolean(),
});

export const CatalogPackSchema = z.strictObject({
  id: z.string(),
  name: LocalizedSchema,
  origin: CatalogOriginSchema,
  source_id: z.string().nullable(),
  listed: z.boolean(),
  replaces_builtin: z.boolean(),
  versions: z.array(CatalogVersionSchema),
});

export const CatalogSourceSchema = z.strictObject({
  id: z.string(),
  kind: SourceKindSchema,
  label: z.string(),
  enabled: z.boolean(),
  replace_builtin: z.boolean(),
  track: z.boolean(),
  packs_path: z.string(),
  url: z.string().nullable(),
  ref: z.string().nullable(),
  access: SourceAccessSchema,
  credential_id: z.string().nullable(),
  service_access_id: z.string().nullable(),
  insecure_http: z.boolean(),
  archive_name: z.string().nullable(),
  archive_digest: z.string().nullable(),
  folder: z.string().nullable(),
  workspace_id: z.string().nullable(),
  applied_revision: z.string().nullable(),
  applied_at: z.string().nullable(),
  checked_revision: z.string().nullable(),
  checked_at: z.string().nullable(),
  check_ok: z.boolean().nullable(),
  // Версии, которые появятся при «Применить» по последней проверке.
  pending_versions: z.number().int(),
  error: CatalogSourceErrorSchema.nullable(),
  busy: z.boolean(),
  created_at: z.string(),
  updated_at: z.string(),
  created_by: z.string().nullable(),
  packs: z.array(CatalogPackSchema),
});

export const CatalogLimitsSchema = z.strictObject({
  max_archive_bytes: z.number().int(),
  max_files: z.number().int(),
  max_bytes: z.number().int(),
});

export const CatalogOverviewSchema = z.strictObject({
  revision: z.number().int(),
  sources: z.array(CatalogSourceSchema),
  // Паки каталога помимо источников: вшитые и оставшиеся от удалённых источников.
  packs: z.array(CatalogPackSchema),
  limits: CatalogLimitsSchema,
});

export const PlannedVersionSchema = z.strictObject({
  template: z.string(),
  version: z.string(),
  verdict: VerdictSchema,
  digest: z.string().nullable(),
  kind: z.string().nullable(),
  min_studio: z.string().nullable(),
  errors: z.array(z.string()),
  warnings: z.array(z.string()),
});

export const PlannedPackSchema = z.strictObject({
  id: z.string(),
  name: LocalizedSchema,
  conflict: ConflictSchema.nullable(),
  conflict_with: z.string().nullable(),
  replaces_builtin: z.boolean(),
  problems: z.array(z.string()),
  versions: z.array(PlannedVersionSchema),
});

export const CatalogCheckSchema = z.strictObject({
  source: CatalogSourceSchema,
  // Проверенная ревизия: «Применить» отправляет именно её.
  revision: z.string(),
  ok: z.boolean(),
  blockers: z.array(BlockerSchema),
  new_count: z.number().int(),
  problems: z.array(z.string()),
  packs: z.array(PlannedPackSchema),
});

export const CatalogApplySchema = z.strictObject({
  source: CatalogSourceSchema,
  revision: z.string(),
  added: z.array(z.string()),
  catalog_revision: z.number().int(),
});

export const CatalogEventSchema = z.strictObject({
  id: z.string(),
  action: EventActionSchema,
  at: z.string(),
  ok: z.boolean(),
  actor_id: z.string().nullable(),
  revision: z.string().nullable(),
  summary: z.record(z.string(), z.unknown()),
});

export const CatalogEventListSchema = z.array(CatalogEventSchema);

export const CreateGitSourceRequestSchema = z.strictObject({
  url: z.string().min(1).max(2048),
  label: z.string().max(200).nullish(),
  packs_path: z.string().max(512).nullish(),
  ref: z.string().max(200).nullish(),
  credential_id: z.string().nullish(),
  service_access_id: z.string().nullish(),
  insecure_http: z.boolean().optional(),
  replace_builtin: z.boolean().optional(),
  track: z.boolean().optional(),
});

export const UpdateSourceRequestSchema = z.strictObject({
  label: z.string().max(200).nullish(),
  packs_path: z.string().max(512).nullish(),
  ref: z.string().max(200).nullish(),
  credential_id: z.string().nullish(),
  service_access_id: z.string().nullish(),
  clear_access: z.boolean().optional(),
  replace_builtin: z.boolean().nullish(),
  track: z.boolean().nullish(),
  enabled: z.boolean().nullish(),
});

export const ApplySourceRequestSchema = z.strictObject({
  revision: z.string().min(1).max(128),
});

export const WorkspaceCatalogSchema = z.strictObject({
  // null: папка рабочего пространства не подключена к каталогу.
  source: CatalogSourceSchema.nullable(),
});

export const WorkspaceCatalogCheckRequestSchema = z.strictObject({
  replace_builtin: z.boolean().optional(),
});

export const CatalogErrorBodySchema = z
  .object({ detail: z.string(), code: z.string() })
  .catchall(z.unknown());

export type SourceKind = z.infer<typeof SourceKindSchema>;
export type SourceAccess = z.infer<typeof SourceAccessSchema>;
export type Verdict = z.infer<typeof VerdictSchema>;
export type Conflict = z.infer<typeof ConflictSchema>;
export type Blocker = z.infer<typeof BlockerSchema>;
export type EventAction = z.infer<typeof EventActionSchema>;
export type CatalogVersion = z.infer<typeof CatalogVersionSchema>;
export type CatalogPack = z.infer<typeof CatalogPackSchema>;
export type CatalogSource = z.infer<typeof CatalogSourceSchema>;
export type CatalogLimits = z.infer<typeof CatalogLimitsSchema>;
export type CatalogOverview = z.infer<typeof CatalogOverviewSchema>;
export type PlannedVersion = z.infer<typeof PlannedVersionSchema>;
export type PlannedPack = z.infer<typeof PlannedPackSchema>;
export type CatalogCheck = z.infer<typeof CatalogCheckSchema>;
export type CatalogApply = z.infer<typeof CatalogApplySchema>;
export type CatalogEvent = z.infer<typeof CatalogEventSchema>;
export type CreateGitSourceRequest = z.infer<
  typeof CreateGitSourceRequestSchema
>;
export type UpdateSourceRequest = z.infer<typeof UpdateSourceRequestSchema>;
export type ApplySourceRequest = z.infer<typeof ApplySourceRequestSchema>;
export type WorkspaceCatalog = z.infer<typeof WorkspaceCatalogSchema>;
export type WorkspaceCatalogCheckRequest = z.infer<
  typeof WorkspaceCatalogCheckRequestSchema
>;
