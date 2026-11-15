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
  // Пространство ходит служебным доступом установки (срез T6): токена человека нет.
  service_access: z.boolean(),
  insecure_http: z.boolean(),
  folder: z.string().nullable(),
  base_branch: z.string().nullable(),
  base_sha: z.string().nullable(),
  fetched_at: z.string().nullable(),
  // Рабочая ветка, PR и последний статус CI (срез T6).
  work_branch: z.string().nullable(),
  pr_url: z.string().nullable(),
  pr_number: z.number().nullable(),
  ci_status: z.string().nullable(),
  // Форк, куда уходит ветка, если в сам репозиторий писать нельзя.
  fork_url: z.string().nullable(),
  // Отправленная вершина: по ней спрашивается статус проверок хостинга.
  pushed_sha: z.string().nullable(),
  error: PackWorkspaceErrorSchema.nullable(),
  created_at: z.string(),
  updated_at: z.string(),
  // Срез T22: пространство над официальным репозиторием паков и когда
  // человек принял его лицензию (до первой отправки null).
  official: z.boolean().optional(),
  license_accepted_at: z.string().nullish(),
});

export const PackWorkspaceListSchema = z.array(PackWorkspaceSchema);

export const CreatePackWorkspaceRequestSchema = z.strictObject({
  kind: z.enum(["git", "folder"]),
  label: z.string().max(120).nullish(),
  url: z.string().max(2048).nullish(),
  credential_id: z.string().nullish(),
  // Служебный доступ установки к этому репозиторию (только сервер).
  service_access: z.boolean().optional(),
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

// Git рабочего пространства (срез T6): ветка, коммит, PR или MR, статус CI.
const ChangeStatusSchema = z.enum(["added", "modified", "deleted"]);

export const PackFileChangeSchema = z.strictObject({
  // Путь от папки паков пространства.
  path: z.string(),
  status: ChangeStatusSchema,
});

export const PackGitSchema = z.strictObject({
  workspace: PackWorkspaceSchema,
  provider: z.enum([
    "github",
    "gitlab",
    "gitea",
    "bitbucket",
    "hse_studio",
    "other",
  ]),
  head_sha: z.string(),
  // null: дерево на вершине базы без ветки.
  branch: z.string().nullable(),
  base_branch: z.string().nullable(),
  // Правки на диске после последнего коммита; dirty это непустой список.
  uncommitted: z.array(PackFileChangeSchema),
  dirty: z.boolean(),
  // Всё, чем пространство отличается от базы (коммиты и правки).
  changed: z.array(PackFileChangeSchema),
  ahead: z.number().int(),
  behind: z.number().int(),
  // Ветка отправлена, PR нет: ссылка «Открыть PR в браузере».
  compare_url: z.string().nullable(),
});

export const PackBranchRequestSchema = z.strictObject({
  name: z.string().min(1).max(200).nullish(),
});

export const PackCommitRequestSchema = z.strictObject({
  message: z.string().max(2000).nullish(),
});

export const PackCommitResponseSchema = z.strictObject({
  git: PackGitSchema,
  sha: z.string().nullable(),
  committed: z.boolean(),
});

export const PackForkChoiceSchema = z.union([
  z.strictObject({ url: z.string().min(1).max(2048) }),
  z.strictObject({ create: z.literal(true) }),
]);

export const PackProposeRequestSchema = z.strictObject({
  title: z.string().max(200).nullish(),
  description: z.string().max(20000).nullish(),
  message: z.string().max(2000).nullish(),
  fork: PackForkChoiceSchema.nullish(),
  // Официальные паки: согласие, что вклад публичен и идёт под лицензией.
  accept_license: z.boolean().optional(),
});

export const PackPullRequestSchema = z.strictObject({
  number: z.number().int(),
  url: z.string(),
  // false: PR из этой ветки уже был открыт.
  created: z.boolean(),
});

// Находка проверки перед отправкой (pack check): файла или каталога, без строки.
export const PackCheckFindingSchema = z.strictObject({
  severity: z.enum(["error", "warning"]),
  check: z.string(),
  path: z.string(),
  message: z.string(),
});

export const PackVersionClassSchema = z.strictObject({
  path: z.string(),
  base: z.string(),
  minimum: z.string(),
  suggested: z.string(),
  by_number: z.string().nullable(),
  headline: LocalizedSchema,
});

export const PackCheckSummarySchema = z.strictObject({
  errors: z.number().int(),
  warnings: z.number().int(),
  findings: z.array(PackCheckFindingSchema),
  classes: z.array(PackVersionClassSchema),
});

export const PackProposeResponseSchema = z.strictObject({
  git: PackGitSchema,
  pushed_sha: z.string(),
  // Куда ушла ветка: сам репозиторий или форк.
  pushed_to: z.string(),
  pull_request: PackPullRequestSchema.nullable(),
  compare_url: z.string().nullable(),
  // Ветка отправлена, а PR открыть не дали (pr_permission_missing).
  pr_error: PackWorkspaceErrorSchema.nullable(),
  checks: PackCheckSummarySchema,
});

export const PackCiCheckSchema = z.strictObject({
  name: z.string(),
  state: z.enum([
    "queued",
    "running",
    "success",
    "failure",
    "neutral",
    "skipped",
    "cancelled",
    // Запуск ждёт одобрения сопровождающего (PR из форка нового участника).
    "awaiting_approval",
  ]),
  url: z.string().nullable(),
  summary: z.string().nullable(),
});

export const PackCiStatusSchema = z.strictObject({
  state: z.enum([
    "none",
    "pending",
    "awaiting_approval",
    "success",
    "failure",
    "unknown",
  ]),
  sha: z.string().nullable(),
  checks: z.array(PackCiCheckSchema),
  // false: хостинг не отдаёт статус этому токену (reason ci_status_unavailable).
  available: z.boolean(),
  reason: z.string().nullable(),
  web_url: z.string().nullable(),
  // Срез T22: открыт, слит или закрыт PR (null: PR нет или хостинг молчит).
  pr_state: z.enum(["open", "merged", "closed"]).nullish(),
});

export const PackStartOverRequestSchema = z.strictObject({
  discard: z.boolean().optional(),
});

export const PackDiffSchema = z.strictObject({
  diff: z.string(),
  truncated: z.boolean(),
});

export const PackServiceAccessSchema = z.strictObject({
  id: z.string(),
  url: z.string(),
  label: z.string(),
  token_family: z.string().nullable(),
  created_by: z.string().nullable(),
  created_by_name: z.string().nullable(),
  created_at: z.string(),
  // Срез T22: доступ бота, ветка уходит только в его форк.
  fork_mode: z.boolean().optional(),
  fork_url: z.string().nullish(),
});

export const PackServiceAccessListSchema = z.array(PackServiceAccessSchema);

export const CreatePackServiceAccessRequestSchema = z.strictObject({
  url: z.string().min(1).max(2048),
  token: z.string().min(1).max(4096),
  label: z.string().max(120).nullish(),
  fork_mode: z.boolean().optional(),
});

export const PackServiceAccessProblemSchema = z.enum([
  "token_rejected",
  "fine_grained_token",
  "scope_missing",
  "fork_unavailable",
  "bot_can_push",
  "provider_unsupported",
]);

export const PackServiceAccessCheckSchema = z.strictObject({
  access: PackServiceAccessSchema,
  ok: z.boolean(),
  login: z.string().nullable(),
  // Области классического токена GitHub; null: хостинг их не назвал.
  scopes: z.array(z.string()).nullable(),
  can_push: z.boolean().nullable(),
  problems: z.array(PackServiceAccessProblemSchema),
});

// ── Срез T22: официальные паки ─────────────────────────────────────────────

export const PackOfficialRepoSchema = z.strictObject({
  url: z.string(),
  web_url: z.string(),
  packs_path: z.string(),
  base_branch: z.string(),
  license: z.string(),
  license_url: z.string(),
  contributing_url: z.string(),
});

export const PackOfficialBotUnavailableSchema = z.enum([
  "local",
  "not_configured",
  "disabled",
  "no_right",
]);

export const PackOfficialSchema = z.strictObject({
  // null: установка не задала официальный репозиторий, кнопки нет.
  repo: PackOfficialRepoSchema.nullable(),
  bot: z.strictObject({
    available: z.boolean(),
    reason: PackOfficialBotUnavailableSchema.nullable(),
    daily_limit: z.number().int().nullable(),
    used: z.number().int().nullable(),
  }),
  workspace_id: z.string().nullable(),
});

export const OpenPackOfficialRequestSchema = z.union([
  z.strictObject({ access: z.literal("bot") }),
  z.strictObject({ access: z.literal("token"), credential_id: z.string() }),
]);

export const PackStudioOfficialAdminSchema = z.strictObject({
  repo: PackOfficialRepoSchema.nullable(),
  bot_enabled: z.boolean(),
  daily_limit: z.number().int(),
  default_daily_limit: z.number().int(),
  service_access: PackServiceAccessSchema.nullable(),
});

export const UpdatePackStudioOfficialRequestSchema = z.strictObject({
  bot_enabled: z.boolean(),
  daily_limit: z.number().int().min(1).max(1000),
});

// Предпросмотр (срез T7): документы версии, переключатели, наборы данных и сборки.
export const PackPreviewDocumentSchema = z.strictObject({
  id: z.string(),
  name: LocalizedSchema,
  kinds: z.array(z.string()),
  staffing: z.array(z.string()),
});

export const PackPreviewSwitchSchema = z.strictObject({
  id: z.string(),
  values: z.array(z.string()),
  default: z.string(),
  label: LocalizedSchema.nullable(),
});

export const PackPreviewExampleSchema = z.strictObject({
  id: z.string(),
  source: z.enum(["file", "auto"]),
  label: LocalizedSchema.nullable(),
  error: z.string().nullable(),
  defaults: z.record(z.string(), z.string()),
});

export const PackPreviewOptionsSchema = z.strictObject({
  workspace_id: z.string(),
  pack: z.string(),
  template: z.string(),
  version: z.string(),
  pack_id: z.string(),
  template_id: z.string(),
  version_id: z.string(),
  documents: z.array(PackPreviewDocumentSchema),
  switches: z.array(PackPreviewSwitchSchema),
  examples: z.array(PackPreviewExampleSchema),
  default_example: z.string(),
  combination: z.record(z.string(), z.string()),
});

export const StartPackPreviewRequestSchema = z.strictObject({
  documents: z.array(z.string()).min(1).max(8),
  example: z.string().max(255).nullish(),
  combination: z.record(z.string(), z.string()).optional(),
});

export const PackPreviewBuildSchema = z.strictObject({
  id: z.string(),
  workspace_id: z.string(),
  pack: z.string(),
  template: z.string(),
  version: z.string(),
  document: z.string(),
  example: z.string(),
  combination: z.record(z.string(), z.string()),
  key: z.string(),
  status: z.enum(["queued", "running", "succeeded", "failed", "cancelled"]),
  cached: z.boolean(),
  created_at: z.string(),
  started_at: z.string().nullable(),
  finished_at: z.string().nullable(),
  pages: z.number().int().nullable(),
  error: z
    .strictObject({ code: z.string(), detail: z.string().nullable() })
    .nullable(),
  source_file: z.string().nullable(),
  has_anchors: z.boolean(),
});

export const PackPreviewStartSchema = z.strictObject({
  builds: z.array(PackPreviewBuildSchema),
});

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
export type PackPreviewOptions = z.infer<typeof PackPreviewOptionsSchema>;
export type PackPreviewBuild = z.infer<typeof PackPreviewBuildSchema>;
export type StartPackPreviewRequest = z.infer<
  typeof StartPackPreviewRequestSchema
>;
export type PackPreviewSwitch = z.infer<typeof PackPreviewSwitchSchema>;
export type PackPreviewExample = z.infer<typeof PackPreviewExampleSchema>;
export type PackPreviewDocument = z.infer<typeof PackPreviewDocumentSchema>;
export type PackFileChange = z.infer<typeof PackFileChangeSchema>;
export type PackGit = z.infer<typeof PackGitSchema>;
export type PackCommitResponse = z.infer<typeof PackCommitResponseSchema>;
export type PackForkChoice = z.infer<typeof PackForkChoiceSchema>;
export type PackProposeRequest = z.infer<typeof PackProposeRequestSchema>;
export type PackProposeResponse = z.infer<typeof PackProposeResponseSchema>;
export type PackCheckFinding = z.infer<typeof PackCheckFindingSchema>;
export type PackVersionClass = z.infer<typeof PackVersionClassSchema>;
export type PackCiCheck = z.infer<typeof PackCiCheckSchema>;
export type PackCiStatus = z.infer<typeof PackCiStatusSchema>;
export type PackDiff = z.infer<typeof PackDiffSchema>;
export type PackServiceAccess = z.infer<typeof PackServiceAccessSchema>;
export type CreatePackServiceAccessRequest = z.infer<
  typeof CreatePackServiceAccessRequestSchema
>;
export type PackServiceAccessCheck = z.infer<
  typeof PackServiceAccessCheckSchema
>;
export type PackServiceAccessProblem = z.infer<
  typeof PackServiceAccessProblemSchema
>;
export type PackOfficial = z.infer<typeof PackOfficialSchema>;
export type PackOfficialRepo = z.infer<typeof PackOfficialRepoSchema>;
export type OpenPackOfficialRequest = z.infer<
  typeof OpenPackOfficialRequestSchema
>;
export type PackStudioOfficialAdmin = z.infer<
  typeof PackStudioOfficialAdminSchema
>;
export type UpdatePackStudioOfficialRequest = z.infer<
  typeof UpdatePackStudioOfficialRequestSchema
>;
