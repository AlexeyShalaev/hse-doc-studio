import { z } from "zod";
import { apiClient, parseResp } from "@shared/api";

// The downloadable bundle (also the body the import endpoint accepts). Inner
// shapes are intentionally loose: the UI round-trips the bundle as-is and never
// reads individual provider/settings fields.
export const ExportBundleSchema = z.object({
  version: z.string(),
  exported_at: z.string(),
  encrypted: z.boolean(),
  settings: z.record(z.string(), z.unknown()).nullable(),
  ai_providers: z.array(z.record(z.string(), z.unknown())),
  // Optional/defaulted so a bundle from an older backend still round-trips.
  agent_personas: z.array(z.record(z.string(), z.unknown())).default([]),
});
export type ExportBundle = z.infer<typeof ExportBundleSchema>;

export const ImportResultSchema = z.object({
  settings_imported: z.boolean(),
  ai_providers_imported: z.number(),
  ai_providers_skipped: z.number(),
  agent_personas_imported: z.number().default(0),
  agent_personas_skipped: z.number().default(0),
  errors: z.array(z.string()),
});
export type ImportResult = z.infer<typeof ImportResultSchema>;

export type MergeStrategy = "skip" | "replace";

export type ExportRequest = {
  include_settings: boolean;
  include_ai_providers: boolean;
  include_agent_personas: boolean;
  encryption_password?: string | null;
};

export type ImportRequest = ExportBundle & {
  merge_strategy: MergeStrategy;
  decryption_password?: string | null;
};

export const exportImportApi = {
  exportData: (request: ExportRequest): Promise<ExportBundle> =>
    apiClient.post("/data/export", request).then(parseResp(ExportBundleSchema)),

  importData: (request: ImportRequest): Promise<ImportResult> =>
    apiClient.post("/data/import", request).then(parseResp(ImportResultSchema)),
};
