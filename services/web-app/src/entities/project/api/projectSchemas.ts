import { z } from "zod";

const ProjectLockSchema = z.object({
  pack_id: z.string(),
  template_id: z.string(),
  version: z.string(),
  engine: z.enum(["xelatex", "pdflatex", "lualatex"]),
});

const AuthorSchema = z.object({
  name: z.string(),
  // Бэкенд (Pydantic) сериализует незаполненные поля как null; .optional()
  // пропускает только undefined — поэтому везде .nullish().
  group: z.string().nullish(),
  // Team mode: folder slug of the author's personal docs ("ivanov").
  slug: z.string().nullish(),
  // Per-author topic (each team member defends their own subtopic).
  topic: z.string().nullish(),
  // false → the author's folder is user-managed, the app won't scaffold it.
  managed: z.boolean().default(true),
  // Author-scoped meta values (doc_code_base, udc, name_en, name_short…).
  meta: z.record(z.string(), z.unknown()).default({}),
});

const PersonSchema = z.object({
  name: z.string(),
  role: z.enum(["university", "company"]),
  title: z.string().nullish(),
  degree: z.string().nullish(),
});

const ChecksOverrideSchema = z.object({
  disabled_categories: z.array(z.string()).default([]),
  disabled: z.array(z.string()).default([]),
  enabled: z.array(z.string()).default([]),
  severity_override: z
    .record(z.string(), z.enum(["info", "warn", "err"]))
    .default({}),
});

export const ProjectResponseSchema = z.object({
  id: z.string(),
  name: z.string(),
  folder: z.string(),
  lock: ProjectLockSchema,
  kind: z.enum(["research", "project"]),
  staffing: z.enum(["solo", "team"]),
  lang: z.enum(["ru", "en"]).optional(),
  authors: z.array(AuthorSchema).optional(),
  supervisor: PersonSchema.nullable().optional(),
  co_supervisor: PersonSchema.nullable().optional(),
  academic_supervisor: PersonSchema.nullable().optional(),
  meta: z.record(z.string(), z.unknown()).optional(),
  created_at: z.string().optional(),
  updated_at: z.string(),
  pinned: z.boolean(),
  archived: z.boolean(),
  checks_override: ChecksOverrideSchema.optional(),
  // Team mode: whether the shared/ docs group exists. Old backends omit it.
  shared_enabled: z.boolean().default(true),
});

export const CreateProjectRequestSchema = z.object({
  name: z.string().min(1),
  folder: z.string().min(1),
  pack_id: z.string().min(1),
  template_id: z.string().min(1),
  version: z.string().min(1),
  engine: z.enum(["xelatex", "pdflatex", "lualatex"]),
  kind: z.enum(["research", "project"]),
  staffing: z.enum(["solo", "team"]),
  lang: z.enum(["ru", "en"]),
  authors: z.array(AuthorSchema),
  supervisor: PersonSchema.nullable().optional(),
  co_supervisor: PersonSchema.nullable().optional(),
  meta: z.record(z.string(), z.unknown()).optional(),
  pres_variant: z.string().optional(),
  shared_enabled: z.boolean().optional(),
});

export const ConnectProjectRequestSchema = z.object({
  folder: z.string().min(1),
});

export const NdaStatusResponseSchema = z.object({
  available: z.boolean(),
  present: z.boolean(),
  files: z.array(z.string()).default([]),
});

// Create-wizard hints aggregated from existing projects.
export const ProjectSuggestionsSchema = z.object({
  folder_roots: z.array(z.object({ path: z.string(), count: z.number() })),
  authors: z.array(z.object({ name: z.string(), group: z.string() })),
});
export type ProjectSuggestions = z.infer<typeof ProjectSuggestionsSchema>;

export const UpdateProjectRequestSchema = z.object({
  name: z.string().optional(),
  lang: z.enum(["ru", "en"]).optional(),
  meta: z.record(z.string(), z.unknown()).optional(),
  authors: z.array(AuthorSchema).optional(),
  supervisor: PersonSchema.nullable().optional(),
  co_supervisor: PersonSchema.nullable().optional(),
  academic_supervisor: PersonSchema.nullable().optional(),
  pinned: z.boolean().optional(),
  archived: z.boolean().optional(),
  checks_override: ChecksOverrideSchema.optional(),
});
