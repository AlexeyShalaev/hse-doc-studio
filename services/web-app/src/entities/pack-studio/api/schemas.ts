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
});

export const PackServiceAccessListSchema = z.array(PackServiceAccessSchema);

export const CreatePackServiceAccessRequestSchema = z.strictObject({
  url: z.string().min(1).max(2048),
  token: z.string().min(1).max(4096),
  label: z.string().max(120).nullish(),
});

export const PackServiceAccessProblemSchema = z.enum([
  "token_rejected",
  "cannot_push",
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

export const PackOfficialSchema = z.strictObject({
  // null: установка не задала официальный репозиторий, кнопки нет.
  repo: PackOfficialRepoSchema.nullable(),
  workspace_id: z.string().nullable(),
});

// Вклад в официальные паки только своим аккаунтом: личный доступ git.
export const OpenPackOfficialRequestSchema = z.strictObject({
  credential_id: z.string(),
});

// Админка: официальный репозиторий из окружения установки, только чтение.
export const PackStudioOfficialAdminSchema = z.strictObject({
  repo: PackOfficialRepoSchema.nullable(),
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
  // Прогнать правила проверок версии на собранном документе (срез T14).
  checks: z.boolean().optional(),
});

export const PackPreviewCheckSchema = z.strictObject({
  rule_id: z.string(),
  severity: z.string(),
  message: z.string(),
  file: z.string().nullable(),
  line: z.number().int().nullable(),
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
  // Сборка с проверками (срез T14); `checks` находки удачной сборки, null: проверок не было.
  with_checks: z.boolean().optional(),
  checks: z.array(PackPreviewCheckSchema).nullish(),
});

export const PackPreviewStartSchema = z.strictObject({
  builds: z.array(PackPreviewBuildSchema),
});

// ── Срез T10: мастер «Новая версия» ──

export const UpdateClassSchema = z.enum(["patch", "minor", "major"]);

/** Пункты по языкам: списки ru и en параллельны (pack_lint). */
export const PackLocalizedListSchema = z.strictObject({
  ru: z.array(z.string()).max(50),
  en: z.array(z.string()).max(50),
});

export const PackVersionNumbersSchema = z.strictObject({
  patch: z.string().nullable(),
  minor: z.string().nullable(),
  major: z.string().nullable(),
});

export const PackVersionChoiceSchema = z.strictObject({
  version: z.string(),
  status: z.string().nullable(),
  // Выпущена в базовой ветке (D10).
  released: z.boolean(),
  // Внесена в реестр рабочего дерева (выпуск в ветке).
  registered: z.boolean(),
  modified: z.boolean(),
});

export const PackVersionOptionsSchema = z.strictObject({
  pack: z.string(),
  template: z.string(),
  versions: z.array(PackVersionChoiceSchema),
  default_base: z.string().nullable(),
  default_version: z.string().nullable(),
  numbers: PackVersionNumbersSchema,
});

export const CreatePackVersionRequestSchema = z.strictObject({
  base: z.string().max(64).nullish(),
  version: z.string().max(64).nullish(),
  update_class: UpdateClassSchema.nullish(),
});

export const PackVersionRefSchema = z.strictObject({
  pack: z.string(),
  template: z.string(),
  version: z.string(),
  path: z.string(),
});

export const PackVersionCreatedSchema = z.strictObject({
  version: PackVersionRefSchema,
  base: z.string(),
  update_class: UpdateClassSchema.nullable(),
  warnings: z.array(z.string()),
});

export const PackVersionReasonSchema = z.strictObject({
  code: z.string(),
  path: z.string(),
  change: z.string(),
  minimum: UpdateClassSchema,
  suggested: UpdateClassSchema,
  hard: z.boolean(),
  exception: z.boolean(),
  message: LocalizedSchema,
});

export const PackVersionStateSchema = z.strictObject({
  version: PackVersionRefSchema,
  status: z.string().nullable(),
  released: z.boolean(),
  // Каталог выпущенной версии отличается от выпуска (7.3, 4.3).
  modified: z.boolean(),
  registered: z.boolean(),
  // Выпуск записан в ветке, а каталог после него правили.
  release_outdated: z.boolean(),
  is_default: z.boolean(),
  base: z.string().nullable(),
  minimum: UpdateClassSchema.nullable(),
  suggested: UpdateClassSchema.nullable(),
  by_number: UpdateClassSchema.nullable(),
  declared: UpdateClassSchema.nullable(),
  note: z.string().nullable(),
  number_ok: z.boolean(),
  headline: LocalizedSchema,
  reasons: z.array(PackVersionReasonSchema),
  numbers: PackVersionNumbersSchema,
  changes: PackLocalizedListSchema,
  breaking_changes: PackLocalizedListSchema,
  draft_changes: PackLocalizedListSchema,
  draft_breaking: PackLocalizedListSchema,
  move_to: z.string().nullable(),
  error: z.string().nullable(),
});

export const PackVersionNotesRequestSchema = z.strictObject({
  changes: PackLocalizedListSchema.nullish(),
  breaking_changes: PackLocalizedListSchema.nullish(),
  note: z.string().max(2000).nullish(),
});

export const PackRenumberRequestSchema = z.strictObject({
  version: z.string().min(1).max(64),
});

export const PackMoveEditsRequestSchema = z.strictObject({
  version: z.string().max(64).nullish(),
});

export const PackVersionMovedSchema = z.strictObject({
  version: PackVersionRefSchema,
  previous: z.string(),
  unreleased: z.boolean(),
  // Выпущенный каталог возвращён к выпуску (git); у папки возвращать нечем.
  restored: z.boolean(),
});

export const PackReleaseRequestSchema = z.strictObject({
  kind: UpdateClassSchema.nullish(),
  set_default: z.boolean().optional(),
});

export const PackReleaseSchema = z.strictObject({
  version: PackVersionRefSchema,
  digest: z.string(),
  kind: UpdateClassSchema.nullable(),
  previous: z.string().nullable(),
  replaced: z.boolean(),
  default_set: z.boolean(),
  edited: z.array(z.string()),
  warnings: z.array(z.string()),
});

// ── Места подписей на PDF предпросмотра (template-studio.md, 5.6, срез T9) ──

const AlignSchema = z.enum(["left", "center", "right"]);
const DateFormatSchema = z.enum([
  "day",
  "month_word",
  "month_number",
  "year",
  "year_short",
  "date_numeric",
  "date_long",
]);

export const PackPlaceBoxSchema = z.strictObject({
  page: z.number().int().min(1),
  x_mm: z.number(),
  y_mm: z.number(),
  width_mm: z.number(),
});

export const PackMarkBoxSchema = z.strictObject({
  page: z.number().int().min(1),
  x_mm: z.number(),
  y_mm: z.number(),
  width_mm: z.number(),
  height_mm: z.number(),
  format: DateFormatSchema,
  align: AlignSchema,
});

// Запись места пака: в мм или на якоре шаблона (та же форма, что у мест пака в состоянии подписей).
export const PackPlaceEntrySchema = z.discriminatedUnion("source", [
  z.strictObject({
    source: z.literal("mm"),
    page: z.number().int(),
    x_mm: z.number(),
    y_mm: z.number(),
    width_mm: z.number(),
  }),
  z.strictObject({
    source: z.literal("anchor"),
    anchor: z.string(),
    align: AlignSchema,
    dx_mm: z.number(),
    dy_mm: z.number(),
    width_mm: z.number().nullable(),
    fallback: PackPlaceBoxSchema.nullable(),
  }),
]);

export const PackDateEntrySchema = z.discriminatedUnion("source", [
  z.strictObject({
    source: z.literal("mm"),
    page: z.number().int(),
    x_mm: z.number(),
    y_mm: z.number(),
    width_mm: z.number(),
    height_mm: z.number(),
    format: DateFormatSchema,
    align: AlignSchema,
  }),
  z.strictObject({
    source: z.literal("anchor"),
    anchor: z.string(),
    format: DateFormatSchema,
    align: AlignSchema,
    height_mm: z.number(),
    width_mm: z.number().nullable(),
    dx_mm: z.number(),
    dy_mm: z.number().nullable(),
    fallback: z
      .strictObject({
        page: z.number().int(),
        x_mm: z.number(),
        y_mm: z.number(),
        width_mm: z.number(),
        height_mm: z.number(),
      })
      .nullable(),
  }),
]);

const PlaceAnchorSchema = z.strictObject({
  id: z.string(),
  state: z.enum(["found", "missing", "unknown"]),
});

export const PackFrameDateSchema = z.strictObject({
  index: z.number().int(),
  entry: PackDateEntrySchema,
  // Рамка в этой сборке; null: метки нет (строки даты в сборке нет).
  box: PackMarkBoxSchema.nullable(),
  anchor: PlaceAnchorSchema.nullable(),
});

export const PackSlotFrameSchema = z.strictObject({
  kind: z.enum(["place", "default"]),
  entry: PackPlaceEntrySchema,
  // Рамка по якорям сборки; null: места в этой сборке нет.
  box: PackPlaceBoxSchema.nullable(),
  anchor: PlaceAnchorSchema.nullable(),
  dates: z.array(PackFrameDateSchema),
});

export const PackSignatureSlotSchema = z.strictObject({
  id: z.string(),
  label: LocalizedSchema,
  applies_to: z.array(z.string()),
  per_author: z.boolean(),
  required: z.boolean(),
  default_place: PackPlaceEntrySchema,
  // Ключа `default_placement` в YAML нет: место по умолчанию лоадера.
  default_set: z.boolean(),
  places: z.record(z.string(), PackPlaceEntrySchema),
  dates: z.record(
    z.string(),
    z.array(
      z.strictObject({ index: z.number().int(), entry: PackDateEntrySchema }),
    ),
  ),
  // Рамки документа сборки; null без сборки или если слот к документу не относится.
  document: PackSlotFrameSchema.nullable(),
});

export const PackSignaturesSchema = z.strictObject({
  workspace_id: z.string(),
  pack: z.string(),
  template: z.string(),
  version: z.string(),
  path: z.string(),
  etag: z.string(),
  read_only: ReadOnlyReasonSchema.nullable(),
  documents: z.array(z.string()),
  build: z
    .strictObject({
      id: z.string(),
      document: z.string(),
      anchors_known: z.boolean(),
      sign_anchors: z.array(z.string()),
      date_anchors: z.array(z.string()),
    })
    .nullable(),
  slots: z.array(PackSignatureSlotSchema),
});

export const PackPlaceOpSchema = z.strictObject({
  op: z.enum([
    "set_place",
    "remove_place",
    "make_default",
    "bind_anchor",
    "unbind_anchor",
    "add_date",
    "set_date",
    "remove_date",
  ]),
  slot: z.string().min(1).max(64),
  doc: z.string().max(128).nullish(),
  box: PackPlaceBoxSchema.nullish(),
  index: z.number().int().min(0).max(64).nullish(),
  mark: PackMarkBoxSchema.nullish(),
  anchor: z.string().max(96).nullish(),
});

export const PackSignaturesPatchRequestSchema = z.strictObject({
  build_id: z.string().nullish(),
  ops: z.array(PackPlaceOpSchema).min(1).max(50),
});

// Срезы T11 и T12: формы версии. Данные манифестов приходят как их читает
// yaml.safe_load (даты строкой), форма разбирает их сама: схема пака богаче
// контракта и растёт без правки этого файла.
const PackModelFileSchema = z.strictObject({
  path: z.string(),
  etag: z.string(),
  data: z.unknown(),
});

export const PackDocFileSchema = z.strictObject({
  path: z.string(),
  bare: z.string(),
  lang: z.string(),
  size: z.number(),
});

export const PackModelDocumentSchema = z.strictObject({
  id: z.string(),
  manifest: PackModelFileSchema.nullable(),
  data: z.unknown(),
  files: z.array(PackDocFileSchema),
  references: z.array(z.string()),
});

export const PackFieldUsageSchema = z.strictObject({
  field: z.string(),
  document: z.string(),
  macros: z.array(z.string()),
  direct: z.boolean(),
  whole: z.boolean(),
});

export const PackVersionModelSchema = z.strictObject({
  workspace_id: z.string(),
  pack: z.string(),
  template: z.string(),
  version: z.string(),
  read_only: ReadOnlyReasonSchema.nullable(),
  manifest: PackModelFileSchema,
  documents: z.array(PackModelDocumentSchema),
  usage: z.array(PackFieldUsageSchema),
  checks: z.array(z.string()),
  problems: z.array(z.string()),
  changed: z.array(z.string()),
});

export const PackModelPatchRequestSchema = z.strictObject({
  file: z.string().min(1).max(300),
  ops: z.array(PackYamlOpSchema).min(1).max(50),
});

export const PackModelActionRequestSchema = z.strictObject({
  action: z.enum([
    "rename_field",
    "add_document",
    "remove_document",
    "add_translation",
  ]),
  field: z.string().nullish(),
  to: z.string().nullish(),
  document: z.string().nullish(),
  name: LocalizedSchema.nullish(),
  source: z.string().nullish(),
  lang: z.string().nullish(),
  files: z.array(z.string()).optional(),
});

export const PackDocLibrarySchema = z.strictObject({
  documents: z.array(
    z.strictObject({
      path: z.string(),
      pack: z.string(),
      template: z.string(),
      version: z.string(),
      id: z.string(),
      name: LocalizedSchema,
    }),
  ),
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
export type UpdateClass = z.infer<typeof UpdateClassSchema>;
export type PackLocalizedList = z.infer<typeof PackLocalizedListSchema>;
export type PackVersionNumbers = z.infer<typeof PackVersionNumbersSchema>;
export type PackVersionChoice = z.infer<typeof PackVersionChoiceSchema>;
export type PackVersionOptions = z.infer<typeof PackVersionOptionsSchema>;
export type CreatePackVersionRequest = z.infer<
  typeof CreatePackVersionRequestSchema
>;
export type PackVersionCreated = z.infer<typeof PackVersionCreatedSchema>;
export type PackVersionReason = z.infer<typeof PackVersionReasonSchema>;
export type PackVersionState = z.infer<typeof PackVersionStateSchema>;
export type PackVersionNotesRequest = z.infer<
  typeof PackVersionNotesRequestSchema
>;
export type PackVersionMoved = z.infer<typeof PackVersionMovedSchema>;
export type PackReleaseRequest = z.infer<typeof PackReleaseRequestSchema>;
export type PackRelease = z.infer<typeof PackReleaseSchema>;
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
export type PackPlaceBox = z.infer<typeof PackPlaceBoxSchema>;
export type PackMarkBox = z.infer<typeof PackMarkBoxSchema>;
export type PackPlaceEntry = z.infer<typeof PackPlaceEntrySchema>;
export type PackDateEntry = z.infer<typeof PackDateEntrySchema>;
export type PackFrameDate = z.infer<typeof PackFrameDateSchema>;
export type PackSlotFrame = z.infer<typeof PackSlotFrameSchema>;
export type PackSignatureSlot = z.infer<typeof PackSignatureSlotSchema>;
export type PackSignatures = z.infer<typeof PackSignaturesSchema>;
export type PackPreviewCheck = z.infer<typeof PackPreviewCheckSchema>;
export type PackPlaceOp = z.infer<typeof PackPlaceOpSchema>;
export type PackSignaturesPatchRequest = z.infer<
  typeof PackSignaturesPatchRequestSchema
>;
export type PackDocFile = z.infer<typeof PackDocFileSchema>;
export type PackModelDocument = z.infer<typeof PackModelDocumentSchema>;
export type PackFieldUsage = z.infer<typeof PackFieldUsageSchema>;
export type PackVersionModel = z.infer<typeof PackVersionModelSchema>;
export type PackModelPatchRequest = z.infer<typeof PackModelPatchRequestSchema>;
export type PackModelActionRequest = z.infer<
  typeof PackModelActionRequestSchema
>;
export type PackDocLibrary = z.infer<typeof PackDocLibrarySchema>;
