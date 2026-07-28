import { z } from "zod";

const ChecksOverrideSchema = z.object({
  disabled_categories: z.array(z.string()).optional(),
  disabled: z.array(z.string()).optional(),
  enabled: z.array(z.string()).optional(),
  severity_override: z
    .record(z.string(), z.enum(["info", "warn", "err"]))
    .optional(),
});

export const CustomFileSchema = z.object({
  original_filename: z.string(),
  ext: z.string(),
  uploaded_at: z.string(),
  convert_to_pdf_at_package: z.boolean().nullable().optional(),
  preview_available: z.boolean(),
});

export const DocumentResponseSchema = z.object({
  // Team-mode personal docs are per-author instances "{def_id}--{slug}"
  // ("vkr--ivanov"); shared/solo docs keep the plain definition id.
  id: z.string(),
  // Pack definition id ("vkr") — the localized document-type name resolves by
  // it, never by the instance id.
  def_id: z.string().nullish(),
  // Owning author's slug / display name (null → shared or solo document).
  owner: z.string().nullish(),
  owner_name: z.string().nullish(),
  // Main .tex / output PDF paths relative to the PROJECT ROOT — in team
  // layouts they carry the base-folder prefix ("shalaev/vkr/vkr.tex").
  source_file: z.string().nullish(),
  output_file: z.string().nullish(),
  // Localized definition name/code straight from the pack — the single source
  // of truth for new doc types (tz_shared); the FE i18n map is a fallback.
  // Empty dicts mean "pack unavailable" and must NOT override the fallback.
  name: z.record(z.string(), z.string()).nullish(),
  code: z.record(z.string(), z.string()).nullish(),
  // GOST reference from the pack definition (detail endpoint).
  gost_ref: z.string().nullish(),
  // Compile engine of the chosen variant ("xelatex", …). null → copy-only
  // variant (pptx/reveal): no LaTeX compilation, «Собрать» just runs the
  // checks and publishes the file.
  engine: z.string().nullish(),
  // Visual nav block from the pack (espd/pdp/pres/…) — the nav draws a thin
  // divider between neighbouring docs of different groups.
  group: z.string().nullish(),
  // PDF preview of a non-PDF artifact (pptx → sibling .pdf produced by the
  // managed Gotenberg container on build and after office-editor saves).
  // null → no preview, download card.
  preview_file: z.string().nullish(),
  // Preview mtime — office-editor saves reconvert the PDF without a compile
  // (last_compile_id stays put), so the viewer refreshes off this stamp.
  preview_updated_at: z.string().nullish(),
  status: z.enum(["draft", "building", "ok", "warn", "err", "locked"]),
  chosen_variant: z.string().nullable().optional(),
  last_compile_id: z.string().nullable().optional(),
  last_compile_at: z.string().nullable().optional(),
  pages: z.number().nullable().optional(),
  warnings: z.number().optional(),
  errors: z.number().optional(),
  checks_override: ChecksOverrideSchema.optional(),
  // Present when the document's normal pack-generated artifact has been
  // replaced with a user-uploaded file (Word/PowerPoint/PDF/anything).
  custom_file: CustomFileSchema.nullable().optional(),
  // Whether the document (custom or template) can currently be signed —
  // false for a non-PDF custom file that has no converted preview yet.
  signing_available: z.boolean().optional(),
});

const CheckFixSchema = z.object({
  file: z.string(),
  search: z.string(),
  replace: z.string(),
  line: z.number().nullable().optional(),
  title: z.string().nullable().optional(),
});

const CheckResultSchema = z.object({
  rule_id: z.string(),
  severity: z.enum(["info", "warn", "err"]),
  message: z.string(),
  location: z
    .object({
      file: z.string(),
      // Backend sends `line: null` for file-level checks (e.g. file_exists,
      // structural). Accept both null and absent.
      line: z.number().nullable().optional(),
    })
    .nullable()
    .optional(),
  // Deterministic one-click fix (typography etc.); absent for most findings.
  fix: CheckFixSchema.nullable().optional(),
  // Present when this rule was auto-suppressed because the document is a
  // custom upload (its engine can't read a .tex source/compile log). A
  // distinct neutral state, not pass/fail/warn.
  status: z.enum(["skipped_custom"]).nullish(),
  skip_reason: z.string().nullish(),
});

export const TriggerCompileResponseSchema = z.object({
  compile_id: z.string(),
});

export const CancelCompileResponseSchema = z.object({
  cancelled_task: z.boolean(),
  record_finalised: z.boolean(),
});

export const CompileListItemSchema = z.object({
  id: z.string(),
  status: z.enum(["pending", "running", "success", "failure", "cancelled"]),
  engine: z.enum(["xelatex", "pdflatex", "lualatex"]),
  started_at: z.string(),
  finished_at: z.string().nullable().optional(),
  pages: z.number().nullable().optional(),
  // Prose word/character totals from texcount (null until a successful build).
  words: z.number().nullable().optional(),
  chars: z.number().nullable().optional(),
  warnings: z.number(),
  errors: z.number(),
});

export const CompileDetailSchema = CompileListItemSchema.extend({
  log: z.string().optional(),
  check_results: z.array(CheckResultSchema).optional(),
});

export const CheckResultsResponseSchema = z.object({
  compile_id: z.string().nullable(),
  results: z.array(CheckResultSchema),
});

export const CheckRuleSchema = z.object({
  rule_id: z.string(),
  title: z.record(z.string(), z.string()),
  category: z.string(),
  effective_severity: z.enum(["info", "warn", "err"]),
  enabled: z.boolean(),
  source: z.string(),
  // Подпись группы приходит из пака (checks/<source>.yaml -> label). Дефолт `{}`
  // держит совместимость со старым бэкендом: UI тогда покажет `source` как есть.
  source_label: z.record(z.string(), z.string()).default({}),
});
