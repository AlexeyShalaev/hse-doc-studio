import { z } from "zod";

// Обновление проекта на новую версию шаблона. Перечислимые значения держим
// строками: незнакомое значение от более новой Студии не должно ронять разбор.

const LocalizedListSchema = z.record(z.string(), z.array(z.string()));

export const TemplateVersionInfoSchema = z.object({
  version: z.string(),
  status: z.string(),
  released_at: z.string(),
  summary: z.record(z.string(), z.string()),
  changes: LocalizedListSchema,
  breaking_changes: LocalizedListSchema,
  released: z.boolean(),
  min_studio: z.string().nullish(),
});

// update_class ∈ patch | minor | major | null
export const AvailableUpdateSchema = z.object({
  version: TemplateVersionInfoSchema,
  update_class: z.string().nullish(),
});

export const TemplateUpdateRecordSchema = z.object({
  id: z.string(),
  from_version: z.string(),
  to_version: z.string(),
  at: z.string(),
  pre_commit: z.string(),
  markers: z.array(z.string()),
  reverted: z.boolean(),
  reverts: z.string().nullish(),
});

export const TemplateUpdateStatusSchema = z.object({
  current_version: z.string(),
  current: TemplateVersionInfoSchema.nullish(),
  digest_mismatch: z.boolean(),
  available: z.array(AvailableUpdateSchema),
  recommended: AvailableUpdateSchema.nullish(),
  last_update: TemplateUpdateRecordSchema.nullish(),
  unresolved_markers: z.array(z.string()),
  in_progress: z.boolean(),
});

// action ∈ update | merge | conflict | add | delete | orphan | user_deleted | ignored
export const TemplateFileOpSchema = z.object({
  path: z.string(),
  action: z.string(),
  binary: z.boolean(),
  doc_id: z.string().nullish(),
  conflicts: z.number(),
  approximate_base: z.boolean(),
  resolutions: z.array(z.string()),
});

export const UpdateWarningSchema = z.object({
  code: z.string(),
  doc_ids: z.array(z.string()),
});

export const TemplateUpdatePlanSchema = z.object({
  from_version: z.string(),
  to_version: z.string(),
  update_class: z.string().nullish(),
  provenance: z.string(),
  fingerprint: z.string(),
  counts: z.record(z.string(), z.number()),
  files: z.array(TemplateFileOpSchema),
  warnings: z.array(UpdateWarningSchema),
});

export const ApplyTemplateUpdateResultSchema = z.object({
  record: TemplateUpdateRecordSchema,
  written: z.array(z.string()),
  deleted: z.array(z.string()),
  markers: z.array(z.string()),
});

export const RevertTemplateUpdateResultSchema = z.object({
  record: TemplateUpdateRecordSchema,
  files: z.array(TemplateFileOpSchema),
  applied: z.boolean(),
  kept: z.array(z.string()),
});

export const TemplateDiffSchema = z.object({
  path: z.string(),
  binary: z.boolean(),
  patch: z.string(),
  truncated: z.boolean(),
});

export const TemplateFileStateSchema = z.object({
  path: z.string(),
  status: z.string(),
  doc_id: z.string().nullish(),
  binary: z.boolean(),
  approximate: z.boolean(),
  ignored: z.boolean(),
});

export const CompareWithTemplateSchema = z.object({
  version: z.string(),
  provenance: z.string(),
  files: z.array(TemplateFileStateSchema),
});

export const TemplateTrackingSchema = z.object({
  ignored: z.array(z.string()),
});

export type TemplateVersionInfo = z.infer<typeof TemplateVersionInfoSchema>;
export type AvailableUpdate = z.infer<typeof AvailableUpdateSchema>;
export type TemplateUpdateRecord = z.infer<typeof TemplateUpdateRecordSchema>;
export type TemplateUpdateStatus = z.infer<typeof TemplateUpdateStatusSchema>;
export type TemplateFileOp = z.infer<typeof TemplateFileOpSchema>;
export type UpdateWarning = z.infer<typeof UpdateWarningSchema>;
export type TemplateUpdatePlan = z.infer<typeof TemplateUpdatePlanSchema>;
export type ApplyTemplateUpdateResult = z.infer<
  typeof ApplyTemplateUpdateResultSchema
>;
export type RevertTemplateUpdateResult = z.infer<
  typeof RevertTemplateUpdateResultSchema
>;
export type TemplateDiff = z.infer<typeof TemplateDiffSchema>;
export type TemplateFileState = z.infer<typeof TemplateFileStateSchema>;
export type CompareWithTemplate = z.infer<typeof CompareWithTemplateSchema>;
