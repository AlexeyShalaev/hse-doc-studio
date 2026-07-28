// ──────────────────────────────────────────────────────────────────────────────
// Shared primitives
// ──────────────────────────────────────────────────────────────────────────────

export type LocalizedString = Record<string, string>;

export type DocumentStatus =
  | "draft"
  | "building"
  | "ok"
  | "warn"
  | "err"
  | "locked";

export type CompileStatus =
  | "pending"
  | "running"
  | "success"
  | "failure"
  | "cancelled";

export type CheckSeverity = "info" | "warn" | "err";

export type TemplateVersionStatus = "stable" | "beta" | "deprecated";

export type ProjectKind = "research" | "project";

export type ProjectStaffing = "solo" | "team";

export type Lang = "ru" | "en";

export type EngineType = "xelatex" | "pdflatex" | "lualatex";

export type PersonRole = "university" | "company";

export type ChangeLogKind =
  | "compile_ok"
  | "compile_fail"
  | "edit"
  | "manual_note"
  | "sign"
  | "pack_submission";

// ──────────────────────────────────────────────────────────────────────────────
// §1 Catalog
// ──────────────────────────────────────────────────────────────────────────────

export type TemplateInfoResponse = {
  id: string;
  name: LocalizedString;
  short_name: LocalizedString;
  icon: string;
  accent_hue: number;
  default_version: string;
};

export type PackResponse = {
  id: string;
  name: LocalizedString;
  description: LocalizedString;
  maintainer: {
    name: string;
    email: string;
  };
  templates: TemplateInfoResponse[];
};

export type VersionListItemResponse = {
  version: string;
  status: TemplateVersionStatus;
  released_at: string;
  summary: LocalizedString;
  is_default: boolean;
};

export type DocumentVariantResponse = {
  id: string;
  label: LocalizedString;
  // Project languages the variant can be chosen in; empty/absent = all.
  supported_langs?: string[];
};

export type DocumentDefinitionResponse = {
  id: string;
  name: LocalizedString;
  code: LocalizedString;
  required: boolean;
  // Team mode: "shared" docs exist once per project, "author" docs get an
  // instance per author ("{def_id}--{slug}"). Default "shared".
  scope?: string;
  // Which staffing modes the definition supports. Default ["solo", "team"].
  supported_staffing?: string[];
  variants: DocumentVariantResponse[];
};

export type MetaFieldDefResponse = {
  type: string;
  label: LocalizedString;
  placeholder?: string;
  required_at?: "create" | "finalize" | "never";
  default?: unknown;
  auto?: string;
  options?: string[];
  // Display group id (see VersionDetailResponse.meta_groups).
  group?: string | null;
  // "author"-scoped fields are edited on the author card (author.meta); the
  // project-level value stays system-wide (used by shared docs). Default
  // "project".
  scope?: "project" | "author";
};

export type MetaGroupDefResponse = {
  id: string;
  label: LocalizedString;
  // Страница настроек проекта: "meta" (по умолчанию) или "documents".
  section?: string;
};

export type SignatureSlotDefResponse = {
  id: string;
  label: LocalizedString;
  applies_to: string[];
  // Обязательности здесь нет: каталог описывает пак вне проекта, а она зависит
  // от контрольной точки. См. RuntimeSignatureSlotResponse.required_by.
  default_placement: {
    page: number;
    x_mm: number;
    y_mm: number;
    width_mm: number;
  };
};

export type SubmissionProfileResponse = {
  id: string;
  name: LocalizedString;
  description: LocalizedString;
  items: {
    doc_id: string;
    signatures: string[];
  }[];
  extra_items: {
    source: string;
    output_name: string;
    format: string;
  }[];
};

export type VersionDetailResponse = {
  version: string;
  status: TemplateVersionStatus;
  // Staffing modes the pack version supports; a pack without "team" cannot be
  // selected for more than one author. Default ["solo"].
  supported_staffing?: string[];
  engine_config: {
    default: EngineType;
    allowed: EngineType[];
    passes: number;
  };
  documents: DocumentDefinitionResponse[];
  meta_fields: Record<string, MetaFieldDefResponse>;
  meta_groups?: MetaGroupDefResponse[];
  signatures: {
    slots: SignatureSlotDefResponse[];
  };
  pack_submission: {
    profiles: SubmissionProfileResponse[];
  };
};

// ──────────────────────────────────────────────────────────────────────────────
// §2 Projects
// ──────────────────────────────────────────────────────────────────────────────

export type AuthorDto = {
  name: string;
  group?: string;
  // Team mode: folder slug the author's personal docs live under ("ivanov").
  slug?: string | null;
  // Per-author topic (each team member defends their own subtopic).
  topic?: string | null;
  // false → the author's folder is user-managed, the app won't scaffold it.
  managed?: boolean;
  // Author-scoped meta values (doc_code_base, udc, name_en, name_short…).
  meta?: Record<string, unknown>;
};

export type PersonDto = {
  name: string;
  role: PersonRole;
  title?: string;
  degree?: string;
};

export type ProjectLockDto = {
  pack_id: string;
  template_id: string;
  version: string;
  engine: EngineType;
};

export type ProjectResponse = {
  id: string;
  name: string;
  folder: string;
  lock: ProjectLockDto;
  kind: ProjectKind;
  staffing: ProjectStaffing;
  lang?: Lang;
  authors?: AuthorDto[];
  supervisor?: PersonDto | null;
  co_supervisor?: PersonDto | null;
  academic_supervisor?: PersonDto | null;
  meta?: Record<string, unknown>;
  created_at?: string;
  updated_at: string;
  pinned: boolean;
  archived: boolean;
  checks_override?: ChecksOverrideDto;
  // Team mode: whether the shared/ docs group exists. Default true.
  shared_enabled?: boolean;
};

export type CreateProjectRequest = {
  name: string;
  folder: string;
  pack_id: string;
  template_id: string;
  version: string;
  engine: EngineType;
  kind: ProjectKind;
  staffing: ProjectStaffing;
  lang: Lang;
  authors: AuthorDto[];
  supervisor?: PersonDto | null;
  co_supervisor?: PersonDto | null;
  meta?: Record<string, unknown>;
  pres_variant?: string;
  shared_enabled?: boolean;
};

export type ConnectProjectRequest = {
  folder: string;
};

export type InspectedProject = {
  id: string;
  name: string;
  pack_id: string;
  template_id: string;
  version: string;
  engine: string;
};

export type InspectResponse = {
  path: string;
  exists: boolean;
  is_dir: boolean;
  has_project: boolean;
  project: InspectedProject | null;
};

export type UpdateProjectRequest = {
  name?: string;
  lang?: Lang;
  meta?: Record<string, unknown>;
  authors?: AuthorDto[];
  supervisor?: PersonDto | null;
  co_supervisor?: PersonDto | null;
  academic_supervisor?: PersonDto | null;
  pinned?: boolean;
  archived?: boolean;
  checks_override?: ChecksOverrideDto;
};

// ──────────────────────────────────────────────────────────────────────────────
// §3 Documents
// ──────────────────────────────────────────────────────────────────────────────

export type ChecksOverrideDto = {
  disabled_categories?: string[];
  disabled?: string[];
  enabled?: string[];
  severity_override?: Record<string, CheckSeverity>;
};

export type CustomFileDto = {
  original_filename: string;
  ext: string;
  uploaded_at: string;
  convert_to_pdf_at_package?: boolean | null | undefined;
  preview_available: boolean;
};

export type DocumentResponse = {
  // Team-mode personal docs are per-author instances: "{def_id}--{slug}"
  // ("vkr--ivanov"); shared/solo docs keep the plain definition id.
  id: string;
  // Pack definition id ("vkr") — resolve the localized document-type name by
  // it, never by the instance id.
  def_id?: string | null;
  // Owning author's slug / display name (null → shared or solo document).
  owner?: string | null;
  owner_name?: string | null;
  // Main .tex / output PDF paths relative to the PROJECT ROOT — in team
  // layouts they carry the base-folder prefix ("shalaev/vkr/vkr.tex").
  source_file?: string | null;
  output_file?: string | null;
  name?: LocalizedString | null;
  code?: LocalizedString | null;
  // GOST reference from the pack definition (detail endpoint).
  gost_ref?: string | null;
  // Compile engine of the chosen variant ("xelatex", …). null → copy-only
  // variant (pptx/reveal): no LaTeX compilation, the build just runs checks
  // and publishes the file.
  engine?: string | null;
  // PDF preview of a non-PDF artifact (pptx -> sibling .pdf produced by the
  // managed Gotenberg container on build and after office-editor saves).
  // null -> no preview, download card.
  preview_file?: string | null;
  // Preview mtime — office-editor saves reconvert the PDF without a compile
  // (last_compile_id stays put), so the viewer refreshes off this stamp.
  preview_updated_at?: string | null;
  status: DocumentStatus;
  chosen_variant?: string | null;
  last_compile_id?: string | null;
  last_compile_at?: string | null;
  pages?: number | null;
  warnings?: number;
  errors?: number;
  checks_override?: ChecksOverrideDto;
  // Present when the document's normal pack-generated artifact has been
  // replaced with a user-uploaded file.
  custom_file?: CustomFileDto | null;
  // Whether the document (custom or template) can currently be signed.
  signing_available?: boolean;
};

export type UpdateDocumentRequest = {
  chosen_variant?: string | null;
  checks_override?: ChecksOverrideDto;
};

// ──────────────────────────────────────────────────────────────────────────────
// §4 Compile
// ──────────────────────────────────────────────────────────────────────────────

export type TriggerCompileResponse = {
  compile_id: string;
};

export type CompileListItemResponse = {
  id: string;
  status: CompileStatus;
  engine: EngineType;
  started_at: string;
  finished_at?: string | null;
  pages?: number | null;
  warnings: number;
  errors: number;
};

export type CheckResultResponse = {
  rule_id: string;
  severity: CheckSeverity;
  message: string;
  location?: {
    file: string;
    line?: number | null;
  } | null;
  // Present when this rule was auto-suppressed because the document is a
  // custom upload — a distinct neutral state, not pass/fail/warn.
  status?: "skipped_custom" | null;
  skip_reason?: string | null;
};

export type CompileDetailResponse = CompileListItemResponse & {
  log?: string;
  check_results?: CheckResultResponse[];
};

export type CompileLogEvent =
  | { type: "log"; data: { line: string; ts: string } }
  | {
      type: "done";
      data: {
        status: "success" | "failure" | "cancelled";
        pages: number | null;
        warnings: number;
        errors: number;
      };
    };

// ──────────────────────────────────────────────────────────────────────────────
// §5 Checks
// ──────────────────────────────────────────────────────────────────────────────

export type CheckResultsResponse = {
  compile_id: string | null;
  results: CheckResultResponse[];
};

export type CheckRuleResponse = {
  rule_id: string;
  title: LocalizedString;
  category: string;
  effective_severity: CheckSeverity;
  enabled: boolean;
  source: string;
  // Подпись группы, объявленная паком (checks/<source>.yaml -> label).
  // Пусто для синтетического "misc" и для паков без шапки.
  source_label: LocalizedString;
};

// ──────────────────────────────────────────────────────────────────────────────
// §6 Signatures
// ──────────────────────────────────────────────────────────────────────────────

export type SignMode =
  | "image"
  | "image_crypto"
  | "crypto_invisible"
  | "detached";

export type SlotInfoResponse = {
  png_path: string | null;
  natural_width_px: number | null;
  natural_height_px: number | null;
  signing_identity_id: string | null;
  sign_mode: SignMode;
  sign_reason: string;
};

export type PlacementResponse = {
  enabled: boolean;
  page: number;
  x_mm: number;
  y_mm: number;
  width_mm: number;
  // ISO «2026-05-12»; штампуется как «12.05.2026» рядом с подписью.
  sign_date?: string | null;
};

// Контрольная точка, требующая подпись этого слота на документе.
export type SignatureProfileRef = {
  id: string;
  name: LocalizedString;
};

// Effective slot set computed by the backend for the CURRENT project. In team
// mode per-author slots are multiplied ("author--ivanov", label already carries
// the name) and applies_to/required_by reference document INSTANCE ids. When
// non-empty, the signatures UI must use these instead of the catalog slot defs
// (whose applies_to are pack definition ids and won't match instances).
export type RuntimeSignatureSlotResponse = {
  id: string;
  label: LocalizedString;
  applies_to: string[];
  // id документа → контрольные точки, требующие подпись. Заменило
  // `required_for: string[]`: обязательность — свойство пары «документ +
  // точка», а не документа.
  required_by: Record<string, SignatureProfileRef[]>;
  default_placement: {
    page: number;
    x_mm: number;
    y_mm: number;
    width_mm: number;
  };
  owner?: string | null;
};

export type SignaturesStateResponse = {
  slots: Record<string, SlotInfoResponse>;
  placements: Record<string, Record<string, PlacementResponse>>;
  runtime_slots?: RuntimeSignatureSlotResponse[];
};

export type UpdatePlacementRequest = {
  // ISO «2026-05-12»; пустая строка очищает дату, undefined — не менять.
  sign_date?: string;
  enabled?: boolean;
  page?: number;
  x_mm?: number;
  y_mm?: number;
  width_mm?: number;
};

export type UploadSignatureResponse = {
  png_path: string;
  natural_width_px: number | null;
  natural_height_px: number | null;
};

// ──────────────────────────────────────────────────────────────────────────────
// §7 Forms (pack-driven form engine — see entities/form for the typed client)
// ──────────────────────────────────────────────────────────────────────────────
// Form schemas + answers are validated with zod in entities/form/api/formApi.ts;
// no hand-written DTOs live here on purpose — the field set is pack-defined.

// ──────────────────────────────────────────────────────────────────────────────
// §8 Submissions
// ──────────────────────────────────────────────────────────────────────────────

export type SubmissionDocItemDto = {
  doc_id: string;
  signatures: string[];
};

export type SubmissionExtraItemDto = {
  source: string;
  output_name: string;
  format: string;
};

export type ArchiveFormatId = "zip" | "targz" | "7z" | "rar";

export type CreateSubmissionRequest = {
  profile_id: string;
  items: SubmissionDocItemDto[];
  extra_items?: SubmissionExtraItemDto[];
  archive_format?: ArchiveFormatId;
  // REQUIRED for team projects: whose submission package is being built (their
  // personal docs + shared docs + their declaration).
  author_slug?: string;
  // doc_id -> convert-to-pdf yes/no, for custom (non-template) documents in
  // this package.
  custom_doc_decisions?: Record<string, boolean>;
};

export type CustomFilePreflightItemDto = {
  doc_id: string;
  doc_name: Record<string, string>;
  original_filename: string;
  ext: string;
  convertible: boolean;
  default_decision?: boolean | null | undefined;
};

// Backend returns a plain JSON array (response_model=list[...]), not a
// wrapped `{items: [...]}` envelope.
export type CustomFilePreflightResponse = CustomFilePreflightItemDto[];

export type SubmissionRecordResponse = {
  id: string;
  profile_id?: string;
  profile_name?: Record<string, string> | null;
  created_at: string;
  output_path?: string | null;
  output_dir?: string | null;
  size_bytes?: number | null;
  archive_format?: string;
  doc_count?: number;
};

// ──────────────────────────────────────────────────────────────────────────────
// §9 Changelog
// ──────────────────────────────────────────────────────────────────────────────

export type ChangeLogEntryResponse = {
  id: string;
  at: string;
  kind: ChangeLogKind;
  doc_id: string | null;
  summary: string;
  note: string | null;
};

export type AddChangeLogEntryRequest = {
  doc_id?: string | null;
  summary: string;
};

// ──────────────────────────────────────────────────────────────────────────────
// §10 Files
// ──────────────────────────────────────────────────────────────────────────────

export type FileTreeItemResponse = {
  path: string;
  size: number;
  modified_at: string;
  /** Template-origin files are protected (false); user-added files are deletable. */
  deletable: boolean;
  /** Directory entry (so empty user folders appear), vs a file. */
  is_dir: boolean;
};

// ──────────────────────────────────────────────────────────────────────────────
// §11 Settings
// ──────────────────────────────────────────────────────────────────────────────

export type SettingsResponse = {
  theme: string;
  // Interface (UI) language — independent from a project's document language.
  interface_language: Lang;
  default_engine: string;
  latex_passes: number;
  // Максимум одновременных docker-сборок; лишние сборки ждут в очереди.
  max_concurrent_compiles: number;
  latex_flags: string | null;
  compile_image: string | null;
  default_ai_provider_id: string | null;
  default_ai_model: string | null;
  agent_auto_approve_writes: boolean;
  agent_enabled_tools: string[] | null;
  default_agent_persona: string | null;
  default_agent_persona_instructions: string | null;
  // Ставить вышедшие обновления самостоятельно; по умолчанию включено.
  auto_update: boolean;
  // Порог (ГБ) освобождаемого места для стартового предупреждения; 0 = выкл.
  disk_usage_warn_gb: number;
};

export type UpdateSettingsRequest = Partial<SettingsResponse>;
