import { z } from "zod";
import { apiClient, parseResp } from "@shared/api";

export const RequirementEntrySchema = z.object({
  id: z.string(),
  title: z.string(),
  source: z.string(),
  referenced_in: z.array(z.string()),
  status: z.enum(["ok", "warn", "err"]),
});

export const RequirementFormatSchema = z.object({
  kind: z.enum(["macro", "id", "custom"]),
  id_pattern: z.string().nullable(),
  definition_docs: z.array(z.string()),
  def_pattern: z.string().nullable(),
  ref_pattern: z.string().nullable(),
});

export const RequirementsMatrixSchema = z.object({
  items: z.array(RequirementEntrySchema),
  format: RequirementFormatSchema,
  format_overridden: z.boolean(),
});

export type RequirementEntry = z.infer<typeof RequirementEntrySchema>;
export type RequirementFormat = z.infer<typeof RequirementFormatSchema>;
export type RequirementsMatrix = z.infer<typeof RequirementsMatrixSchema>;

export const requirementsApi = {
  get: (projectId: string) =>
    apiClient
      .get(`/projects/${projectId}/requirements`)
      .then(parseResp(RequirementsMatrixSchema)),

  // null format → reset the project override back to the pack template default.
  updateFormat: (projectId: string, format: RequirementFormat | null) =>
    apiClient
      .put(`/projects/${projectId}/requirements/format`, { format })
      .then(parseResp(RequirementsMatrixSchema)),
};
