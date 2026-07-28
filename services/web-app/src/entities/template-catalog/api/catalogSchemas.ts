import { z } from "zod";

const LocalizedStringSchema = z.record(z.string(), z.string());

const TemplateInfoSchema = z.object({
  id: z.string(),
  name: LocalizedStringSchema,
  short_name: LocalizedStringSchema,
  icon: z.string(),
  accent_hue: z.number(),
  default_version: z.string(),
});

export const PackResponseSchema = z.object({
  id: z.string(),
  name: LocalizedStringSchema,
  description: LocalizedStringSchema,
  maintainer: z.object({
    name: z.string(),
    email: z.string(),
  }),
  templates: z.array(TemplateInfoSchema),
});

export const VersionListItemSchema = z.object({
  version: z.string(),
  status: z.enum(["stable", "beta", "deprecated"]),
  released_at: z.string(),
  summary: LocalizedStringSchema,
  is_default: z.boolean(),
});

const DocumentVariantSchema = z.object({
  id: z.string(),
  label: LocalizedStringSchema,
  source_file: z.string().nullish(),
  output_file: z.string().nullish(),
  // Project languages the variant can be chosen in (IEEE/ISO editions of the
  // ESPD docs are en-only). Empty = available in every language.
  supported_langs: z.array(z.string()).default([]),
});

const DocumentDefinitionSchema = z.object({
  id: z.string(),
  name: LocalizedStringSchema,
  code: LocalizedStringSchema,
  required: z.boolean(),
  source_file: z.string().nullish(),
  output_file: z.string().nullish(),
  gost_ref: z.string().nullish(),
  supported_langs: z.array(z.string()).default([]),
  // Team mode: "shared" docs exist once per project, "author" docs get an
  // instance per author ("{def_id}--{slug}").
  scope: z.string().default("shared"),
  // Which staffing modes the definition supports.
  supported_staffing: z.array(z.string()).default(["solo", "team"]),
  // Which work kinds the definition exists in ("research"/"project"); empty or
  // both = document exists in every kind.
  supported_kinds: z.array(z.string()).default(["research", "project"]),
  variants: z.array(DocumentVariantSchema),
});

export const MetaFieldDefSchema = z.object({
  type: z.string(),
  label: LocalizedStringSchema,
  // Backend serialises Python `Optional[X] = None` as JSON `null`. zod's
  // .optional() only allows `undefined`, so we use .nullish() (accepts both)
  // for every field the API may return as null.
  placeholder: z.string().nullish(),
  required_at: z.enum(["create", "finalize", "never"]).nullish(),
  help: LocalizedStringSchema.nullish(),
  // Static pre-fill value (degree type, programme…). `default` is Any on the
  // backend; for our fields it's always a string, but keep it lenient.
  default: z.unknown().nullish(),
  // Computed pre-fill kind the wizard resolves at creation (e.g. academic_year).
  auto: z.string().nullish(),
  options: z.array(z.string()).nullish(),
  // Display group id (see VersionDetail.meta_groups).
  group: z.string().nullish(),
  // "author"-scoped fields are edited on the author card (author.meta); the
  // project-level value stays system-wide (used by shared docs).
  scope: z.enum(["project", "author"]).default("project"),
  // Which work kinds show this field ("research"/"project"); empty/both = all.
  // E.g. `manuals` (РП/РО) is project-only — hidden in research projects.
  supported_kinds: z.array(z.string()).default(["research", "project"]),
});

export const MetaGroupDefSchema = z.object({
  id: z.string(),
  label: LocalizedStringSchema,
  // Страница настроек проекта, на которой пак просит показать группу: "meta"
  // («Метаданные», по умолчанию) или "documents" («Документы»).
  section: z.string().default("meta"),
});

const SignatureSlotDefSchema = z.object({
  id: z.string(),
  label: LocalizedStringSchema,
  applies_to: z.array(z.string()),
  // Обязательности здесь нет: каталог описывает пак вне проекта, а она зависит
  // от контрольной точки — см. runtime_slots[].required_by в подписях проекта.
  default_placement: z.object({
    page: z.number(),
    x_mm: z.number(),
    y_mm: z.number(),
    width_mm: z.number(),
  }),
});

const SubmissionProfileSchema = z.object({
  id: z.string(),
  name: LocalizedStringSchema,
  description: LocalizedStringSchema,
  items: z
    .array(
      z.object({
        doc_id: z.string(),
        signatures: z.array(z.string()),
      }),
    )
    .nullish(),
  extra_items: z
    .array(
      z.object({
        source: z.string(),
        output_name: z.string(),
        format: z.string(),
      }),
    )
    .nullish(),
});

export type MetaFieldDef = z.infer<typeof MetaFieldDefSchema>;

export const VersionDetailSchema = z.object({
  version: z.string(),
  status: z.enum(["stable", "beta", "deprecated"]),
  // Staffing modes the pack version supports; a pack without "team" cannot be
  // selected for more than one author.
  supported_staffing: z.array(z.string()).default(["solo"]),
  engine_config: z.object({
    default: z.enum(["xelatex", "pdflatex", "lualatex"]),
    allowed: z.array(z.enum(["xelatex", "pdflatex", "lualatex"])),
    passes: z.number(),
  }),
  documents: z.array(DocumentDefinitionSchema),
  meta_fields: z.record(z.string(), MetaFieldDefSchema),
  meta_groups: z.array(MetaGroupDefSchema).default([]),
  signatures: z.object({
    slots: z.array(SignatureSlotDefSchema),
  }),
  pack_submission: z.object({
    profiles: z.array(SubmissionProfileSchema),
  }),
});
