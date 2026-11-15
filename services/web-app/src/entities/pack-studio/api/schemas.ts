import { z } from "zod";

// Контракт Студии шаблонов (contracts/pack-studio). Эталонные JSON разбирают и эти
// схемы (contract.test.ts), и строгие модели бэкенда. Форму меняют так: сначала
// эталоны, затем обе стороны и оба набора тестов в одном коммите.

const LocalizedSchema = z.record(z.string(), z.string());

export const PackStudioSectionSchema = z.strictObject({
  enabled: z.boolean(),
  // Включение задано окружением или профилем standalone: переключатель только для чтения.
  locked: z.boolean(),
  // Раздел открыт человеку: включён и есть право «Автор шаблонов».
  allowed: z.boolean(),
  has_right: z.boolean(),
  standalone: z.boolean(),
});

export const PackWorkspaceErrorSchema = z.strictObject({
  // Код из contracts/pack-studio/error_codes.json или contracts/git-sync/error_codes.json.
  code: z.string(),
  detail: z.string(),
});

export const PackWorkspaceSchema = z.strictObject({
  id: z.string(),
  kind: z.enum(["git", "folder"]),
  label: z.string(),
  state: z.enum(["cloning", "ready", "failed"]),
  // Идёт фоновая операция: клон или выборка базовой ветки.
  busy: z.boolean(),
  packs_path: z.string(),
  url: z.string().nullable(),
  credential_id: z.string().nullable(),
  insecure_http: z.boolean(),
  folder: z.string().nullable(),
  base_branch: z.string().nullable(),
  base_sha: z.string().nullable(),
  fetched_at: z.string().nullable(),
  // Ветка, PR и статус CI появятся со срезом T6.
  work_branch: z.string().nullable(),
  pr_url: z.string().nullable(),
  pr_number: z.number().nullable(),
  ci_status: z.string().nullable(),
  error: PackWorkspaceErrorSchema.nullable(),
  created_at: z.string(),
  updated_at: z.string(),
});

export const PackWorkspaceListSchema = z.array(PackWorkspaceSchema);

export const CreatePackWorkspaceRequestSchema = z.strictObject({
  kind: z.enum(["git", "folder"]),
  label: z.string().max(120).nullish(),
  url: z.string().max(2048).nullish(),
  credential_id: z.string().nullish(),
  insecure_http: z.boolean().optional(),
  base_branch: z.string().max(255).nullish(),
  folder: z.string().max(4096).nullish(),
  packs_path: z.string().max(1024).nullish(),
});

const ReadOnlyReasonSchema = z.enum(["version_released", "releases_read_only"]);

export const PackTreeVersionSchema = z.strictObject({
  version: z.string(),
  path: z.string(),
  status: z.string().nullable(),
  released: z.boolean(),
  // Каталог выпущенной версии правили мимо Студии: дайджест не совпадает с реестром.
  modified: z.boolean(),
});

export const PackTreeTemplateSchema = z.strictObject({
  id: z.string(),
  path: z.string(),
  name: LocalizedSchema.nullable(),
  default_version: z.string().nullable(),
  versions: z.array(PackTreeVersionSchema),
});

export const PackTreePackSchema = z.strictObject({
  id: z.string(),
  path: z.string(),
  name: LocalizedSchema.nullable(),
  templates: z.array(PackTreeTemplateSchema),
});

export const PackTreeFileSchema = z.strictObject({
  path: z.string(),
  is_dir: z.boolean(),
  size: z.number(),
  read_only: ReadOnlyReasonSchema.nullable(),
});

export const PackTreeSchema = z.strictObject({
  workspace_id: z.string(),
  base_sha: z.string().nullable(),
  packs: z.array(PackTreePackSchema),
  files: z.array(PackTreeFileSchema),
  truncated: z.boolean(),
});

export const PackFileVersionSchema = z.strictObject({
  path: z.string(),
  etag: z.string(),
  size: z.number(),
});

const YamlPathSchema = z.array(z.union([z.string(), z.number().int()]));

export const PackYamlOpSchema = z.strictObject({
  op: z.enum(["set", "insert", "delete", "move"]),
  path: YamlPathSchema,
  value: z.unknown().optional(),
  index: z.number().int().nullish(),
  to: z.number().int().nullish(),
});

export const PackYamlPatchRequestSchema = z.strictObject({
  ops: z.array(PackYamlOpSchema).min(1).max(200),
});

export const PackYamlPatchResponseSchema = z.strictObject({
  path: z.string(),
  etag: z.string(),
  size: z.number(),
  content: z.string(),
});

// Тело ошибки: {detail, code} и поля по коду (etag и content у stale_file, path у
// version_released, op и reason у yaml_patch_conflict, limit у file_too_large).
export const PackStudioErrorBodySchema = z
  .object({ detail: z.string(), code: z.string() })
  .catchall(z.unknown());

export const PackDiagnosticSchema = z.strictObject({
  severity: z.enum(["error", "warning"]),
  check: z.enum(["lint", "schema"]),
  message: z.string(),
  // Файл находки от папки паков; null: версия целиком.
  path: z.string().nullable(),
  line: z.number().int().nullable(),
  pointer: z.string().nullable(),
});

export const PackLintRequestSchema = z.strictObject({
  path: z.string().min(1).max(1024),
});

export const PackLintSchema = z.strictObject({
  scope: z.enum(["version", "file", "none"]),
  target: z.string().nullable(),
  released: z.boolean(),
  errors: z.number().int(),
  warnings: z.number().int(),
  findings: z.array(PackDiagnosticSchema),
});

export const PackMetaFieldHintSchema = z.strictObject({
  key: z.string(),
  type: z.string().nullable(),
  label: LocalizedSchema.nullable(),
  group: z.string().nullable(),
});

export const PackMacroHintSchema = z.strictObject({
  name: z.string(),
  keys: z.array(z.string()),
  source: z.string(),
});

export const PackEditorHintsSchema = z.strictObject({
  version: z.string().nullable(),
  meta_fields: z.array(PackMetaFieldHintSchema),
  macros: z.array(PackMacroHintSchema),
});

export const UpdatePackStudioSectionRequestSchema = z.strictObject({
  enabled: z.boolean(),
});

export const PackStudioGrantSchema = z.strictObject({
  id: z.string(),
  subject: z.enum(["user", "group"]),
  subject_id: z.string(),
  name: z.string().nullable(),
  email: z.string().nullable(),
  org_slug: z.string().nullable(),
  org_name: z.string().nullable(),
  granted_by: z.string().nullable(),
  created_at: z.string(),
});

export const PackStudioAdminSchema = z.strictObject({
  enabled: z.boolean(),
  locked: z.boolean(),
  grants: z.array(PackStudioGrantSchema),
});

export const UpdatePackStudioAdminRequestSchema = z.strictObject({
  enabled: z.boolean(),
});

export const CreatePackStudioGrantRequestSchema = z.union([
  z.strictObject({ user_id: z.string().min(1).max(64) }),
  z.strictObject({ group_id: z.string().min(1).max(64) }),
]);

export type PackStudioSection = z.infer<typeof PackStudioSectionSchema>;
export type PackWorkspace = z.infer<typeof PackWorkspaceSchema>;
export type CreatePackWorkspaceRequest = z.infer<
  typeof CreatePackWorkspaceRequestSchema
>;
export type PackTree = z.infer<typeof PackTreeSchema>;
export type PackTreePack = z.infer<typeof PackTreePackSchema>;
export type PackTreeTemplate = z.infer<typeof PackTreeTemplateSchema>;
export type PackTreeVersion = z.infer<typeof PackTreeVersionSchema>;
export type PackTreeFile = z.infer<typeof PackTreeFileSchema>;
export type PackReadOnlyReason = z.infer<typeof ReadOnlyReasonSchema>;
export type PackFileVersion = z.infer<typeof PackFileVersionSchema>;
export type PackYamlOp = z.infer<typeof PackYamlOpSchema>;
export type PackYamlPatchResponse = z.infer<typeof PackYamlPatchResponseSchema>;
export type PackDiagnostic = z.infer<typeof PackDiagnosticSchema>;
export type PackLint = z.infer<typeof PackLintSchema>;
export type PackMetaFieldHint = z.infer<typeof PackMetaFieldHintSchema>;
export type PackMacroHint = z.infer<typeof PackMacroHintSchema>;
export type PackEditorHints = z.infer<typeof PackEditorHintsSchema>;
export type PackStudioGrant = z.infer<typeof PackStudioGrantSchema>;
export type PackStudioAdmin = z.infer<typeof PackStudioAdminSchema>;
export type CreatePackStudioGrantRequest = z.infer<
  typeof CreatePackStudioGrantRequestSchema
>;
