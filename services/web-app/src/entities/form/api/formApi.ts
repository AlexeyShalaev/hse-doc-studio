import { z } from "zod";
import { apiClient, parseResp } from "@shared/api";

const LocalizedSchema = z.record(z.string(), z.string());

// Backend serialises Python `Optional[X] = None` as JSON `null`. zod's
// .optional() only accepts `undefined`, so every nullable field uses .nullish()
// (accepts both null and undefined) — the same convention as catalogSchemas.ts.

const FormOptionSchema = z.object({
  id: z.string(),
  label: LocalizedSchema,
  default: z.boolean().default(false),
});

const FormColumnSchema = z.object({
  id: z.string(),
  label: LocalizedSchema,
});

const VisibleIfSchema = z.object({
  field: z.string(),
  equals: z.unknown(),
});

const FormFieldSchema = z.object({
  id: z.string(),
  type: z.string(),
  label: LocalizedSchema,
  help: LocalizedSchema.nullish(),
  placeholder: LocalizedSchema.nullish(),
  required: z.boolean().default(false),
  options: z.array(FormOptionSchema).default([]),
  columns: z.array(FormColumnSchema).default([]),
  min: z.number().nullish(),
  max: z.number().nullish(),
  step: z.number().nullish(),
  min_length: z.number().nullish(),
  default: z.unknown().nullish(),
  widget: z.string().nullish(),
  visible_if: VisibleIfSchema.nullish(),
  content: LocalizedSchema.nullish(),
});

const FormSectionSchema = z.object({
  id: z.string(),
  title: LocalizedSchema,
  fields: z.array(FormFieldSchema),
});

const FormErrorSchema = z.object({
  field_id: z.string(),
  message: z.string(),
});

export const FormResponseSchema = z.object({
  id: z.string(),
  title: LocalizedSchema,
  schema_version: z.number(),
  required_for_pack: z.boolean(),
  sections: z.array(FormSectionSchema),
  answers: z.record(z.string(), z.unknown()),
  completed: z.boolean(),
  complete: z.boolean(),
  errors: z.array(FormErrorSchema),
});

const FormListItemSchema = z.object({
  // Team-mode per-author forms are instances "ai_declaration--{slug}".
  id: z.string(),
  title: LocalizedSchema,
  required_for_pack: z.boolean(),
  completed: z.boolean(),
  complete: z.boolean(),
  icon: z.string().nullish(),
  // Owning author's slug for per-author form instances (title already carries
  // the name); null → project-wide form.
  owner: z.string().nullish(),
});

export const FormListResponseSchema = z.object({
  forms: z.array(FormListItemSchema),
});

export const FormPreviewResponseSchema = z.object({
  output_name: z.string(),
  format: z.string(),
  content: z.string(),
});

export type FormOption = z.infer<typeof FormOptionSchema>;
export type FormColumn = z.infer<typeof FormColumnSchema>;
export type FormFieldDef = z.infer<typeof FormFieldSchema>;
export type FormSection = z.infer<typeof FormSectionSchema>;
export type FormError = z.infer<typeof FormErrorSchema>;
export type FormData = z.infer<typeof FormResponseSchema>;
export type FormListItem = z.infer<typeof FormListItemSchema>;
export type FormPreview = z.infer<typeof FormPreviewResponseSchema>;
export type FormAnswers = Record<string, unknown>;

export type UpdateFormRequest = {
  completed?: boolean;
  answers?: FormAnswers;
};

export const formApi = {
  list: (projectId: string) =>
    apiClient
      .get(`/projects/${projectId}/forms`)
      .then(parseResp(FormListResponseSchema)),

  get: (projectId: string, formId: string) =>
    apiClient
      .get(`/projects/${projectId}/forms/${formId}`)
      .then(parseResp(FormResponseSchema)),

  update: (projectId: string, formId: string, body: UpdateFormRequest) =>
    apiClient
      .put(`/projects/${projectId}/forms/${formId}`, body)
      .then(parseResp(FormResponseSchema)),

  preview: (projectId: string, formId: string) =>
    apiClient
      .get(`/projects/${projectId}/forms/${formId}/preview`)
      .then(parseResp(FormPreviewResponseSchema)),
};
