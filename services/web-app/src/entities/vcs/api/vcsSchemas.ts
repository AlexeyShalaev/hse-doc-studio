import { z } from "zod";

export const VcsCommitStatsSchema = z.object({
  files: z.number(),
  insertions: z.number(),
  deletions: z.number(),
});

export const VcsRefSchema = z.object({
  name: z.string(),
  kind: z.string(),
});

// kind ∈ init | edit | compile | manual | restore (kept as string so an
// unknown future kind never breaks parsing).
export const VcsCommitSchema = z.object({
  id: z.string(),
  short_id: z.string(),
  kind: z.string(),
  message: z.string(),
  author: z.string(),
  created_at: z.string(),
  parents: z.array(z.string()),
  refs: z.array(VcsRefSchema),
  doc_id: z.string().nullish(),
  stats: VcsCommitStatsSchema.nullish(),
});

export const VcsFileChangeSchema = z.object({
  path: z.string(),
  change: z.string(),
  old_path: z.string().nullish(),
});

export const VcsCommitDetailSchema = z.object({
  commit: VcsCommitSchema,
  files: z.array(VcsFileChangeSchema),
});

export const VcsStatusSchema = z.object({
  available: z.boolean(),
  initialized: z.boolean(),
  current_branch: z.string().nullable(),
  head: z.string().nullable(),
  dirty: z.boolean(),
  modified: z.number(),
  untracked: z.number(),
  staged: z.number(),
  last_snapshot_at: z.string().nullable(),
  store_path: z.string(),
  tracking_enabled: z.boolean(),
});

export const VcsFileDiffSchema = z.object({
  path: z.string(),
  change: z.string(),
  patch: z.string(),
  binary: z.boolean(),
});

export const VcsDiffSchema = z.object({
  from_id: z.string().nullable(),
  to_id: z.string().nullable(),
  files: z.array(VcsFileDiffSchema),
  truncated: z.boolean(),
});

export const VcsRestoreSchema = z.object({
  restored_from: z.string(),
  new_snapshot_id: z.string().nullable(),
  pre_snapshot_id: z.string().nullable(),
  files_changed: z.number(),
});

export const VcsSettingsSchema = z.object({
  tracking_enabled: z.boolean(),
  auto_commit_on_compile: z.boolean(),
  track_pdf: z.boolean(),
});

export const VcsBranchSchema = z.object({
  name: z.string(),
  head: z.string(),
  is_current: z.boolean(),
  is_protected: z.boolean().default(false),
  created_at: z.string().nullish(),
});

// kind ∈ tag | release
export const VcsTagSchema = z.object({
  name: z.string(),
  commit_id: z.string(),
  kind: z.string(),
  message: z.string().nullish(),
  created_at: z.string().nullish(),
});

export type VcsCommit = z.infer<typeof VcsCommitSchema>;
export type VcsCommitDetail = z.infer<typeof VcsCommitDetailSchema>;
export type VcsStatus = z.infer<typeof VcsStatusSchema>;
export type VcsDiff = z.infer<typeof VcsDiffSchema>;
export type VcsFileDiff = z.infer<typeof VcsFileDiffSchema>;
export type VcsRestore = z.infer<typeof VcsRestoreSchema>;
export type VcsSettings = z.infer<typeof VcsSettingsSchema>;
export type VcsBranch = z.infer<typeof VcsBranchSchema>;
export type VcsTag = z.infer<typeof VcsTagSchema>;
