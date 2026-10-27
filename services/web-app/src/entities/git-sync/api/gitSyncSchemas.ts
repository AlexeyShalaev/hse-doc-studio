import { z } from "zod";

import { VcsHistoryFacetsSchema } from "@entities/vcs";

// Контракт Git-синхронизации (contracts/git-sync). Перечислимые значения держим
// строками: незнакомое значение от более новой Студии не должно ронять разбор.
// Допустимые значения перечислены типами ниже, проверяются хелперами is*.

// --- известные значения ---------------------------------------------------------

export const GIT_UI_STATES = [
  "no_remote",
  "unfetched",
  "up_to_date",
  "ahead",
  "behind",
  "diverged",
  "syncing",
  "conflicts",
  "auth_failed",
  "offline",
  "error",
  "blocked",
] as const;
export type GitUiState = (typeof GIT_UI_STATES)[number];

export const GIT_HEALTH = [
  "ok",
  "unauthenticated",
  "offline",
  "error",
  "host_key_changed",
  "remote_missing",
  "branch_missing",
] as const;
export type GitHealth = (typeof GIT_HEALTH)[number];

export const GIT_RELATIONS = [
  "none",
  "unfetched",
  "remote_empty",
  "in_sync",
  "ahead",
  "behind",
  "diverged",
] as const;
export type GitRelation = (typeof GIT_RELATIONS)[number];

export const GIT_BLOCKED_REASONS = [
  "off_branch",
  "read_only",
  "remote_schema_newer",
  "store_untrusted",
  "profile_required",
] as const;
export type GitBlockedReason = (typeof GIT_BLOCKED_REASONS)[number];

export const GIT_OPERATION_KINDS = [
  "sync",
  "resolve",
  "connect",
  "clone",
  "bundle_import",
] as const;
export type GitOperationKind = (typeof GIT_OPERATION_KINDS)[number];

export const GIT_OPERATION_STATUSES = [
  "running",
  "succeeded",
  "failed",
  "cancelled",
] as const;
export type GitOperationStatus = (typeof GIT_OPERATION_STATUSES)[number];

export const GIT_OPERATION_PHASES = [
  "queued",
  "snapshot",
  "fetch",
  "merge",
  "push",
  "download",
  "verify",
  "register",
] as const;
export type GitOperationPhase = (typeof GIT_OPERATION_PHASES)[number];

export const GIT_SYNC_OUTCOMES = [
  "up_to_date",
  "pushed",
  "fast_forwarded",
  "merged",
  "conflicts",
] as const;
export type GitSyncOutcome = (typeof GIT_SYNC_OUTCOMES)[number];

export const GIT_AUTO_ACTIONS = [
  "take_theirs",
  "merged",
  "delete",
  "binary_newest",
] as const;
export type GitAutoAction = (typeof GIT_AUTO_ACTIONS)[number];

export const GIT_WARNING_CODES = [
  "template_missing_after_merge",
  "unsafe_path",
  "case_collision",
  "signatures_stale",
  "frozen_documents",
  "team_foreign_edit",
  "template_missing",
  "lfs_pointers",
] as const;
export type GitWarningCode = (typeof GIT_WARNING_CODES)[number];

export const GIT_CONFLICT_TYPES = [
  "content",
  "fields",
  "deleted_by_us",
  "deleted_by_them",
  "add_add",
  "binary",
  "signature_group",
  "case_collision",
  "invalid_result",
] as const;
export type GitConflictType = (typeof GIT_CONFLICT_TYPES)[number];

export const GIT_CONFLICT_ACTIONS = [
  "conflict",
  "binary_newest",
  "merged",
  "take_theirs",
  "delete",
] as const;
export type GitConflictAction = (typeof GIT_CONFLICT_ACTIONS)[number];

export const GIT_COMMIT_SYNC_MARKS = [
  "pushed",
  "unpushed",
  "incoming",
] as const;
export type GitCommitSyncMark = (typeof GIT_COMMIT_SYNC_MARKS)[number];

const isOneOf =
  <T extends string>(values: readonly T[]) =>
  (value: unknown): value is T =>
    typeof value === "string" && (values as readonly string[]).includes(value);

export const isGitUiState = isOneOf(GIT_UI_STATES);
export const isGitHealth = isOneOf(GIT_HEALTH);
export const isGitRelation = isOneOf(GIT_RELATIONS);
export const isGitBlockedReason = isOneOf(GIT_BLOCKED_REASONS);
export const isGitOperationKind = isOneOf(GIT_OPERATION_KINDS);
export const isGitOperationStatus = isOneOf(GIT_OPERATION_STATUSES);
export const isGitOperationPhase = isOneOf(GIT_OPERATION_PHASES);
export const isGitSyncOutcome = isOneOf(GIT_SYNC_OUTCOMES);
export const isGitAutoAction = isOneOf(GIT_AUTO_ACTIONS);
export const isGitWarningCode = isOneOf(GIT_WARNING_CODES);
export const isGitConflictType = isOneOf(GIT_CONFLICT_TYPES);
export const isGitConflictAction = isOneOf(GIT_CONFLICT_ACTIONS);
export const isGitCommitSyncMark = isOneOf(GIT_COMMIT_SYNC_MARKS);

// --- ошибки ---------------------------------------------------------------------

export const GitHostKeySchema = z.object({
  type: z.string(),
  fingerprint_sha256: z.string(),
});

// Сертификат, который предъявил сервер: по нему решают, добавить CA или закрепить отпечаток.
export const GitTlsCertificateSchema = z.object({
  fingerprint_sha256: z.string(),
  subject: z.string(),
  issuer: z.string(),
  not_before: z.string(),
  not_after: z.string(),
  self_signed: z.boolean(),
});

export const GIT_DETECTED_BY = ["override", "host", "api", "unknown"] as const;
export type GitDetectedBy = (typeof GIT_DETECTED_BY)[number];
export const isGitDetectedBy = (value: unknown): value is GitDetectedBy =>
  typeof value === "string" &&
  (GIT_DETECTED_BY as readonly string[]).includes(value);

// Что за сервер и как это узнали: выбор человека, имя хоста, ответ API или никак.
export const GitProviderInfoSchema = z.object({
  id: z.string(), // github | gitlab | gitea | bitbucket | other
  detected_by: z.string(), // override | host | api | unknown
  version: z.string().nullish(),
});

export const GitCredentialUsageSchema = z.object({
  project_id: z.string(),
  name: z.string(),
});

// {detail, code} и дополнительные поля конкретного кода.
export const GitErrorBodySchema = z.object({
  detail: z.string(),
  code: z.string(),
  operation_id: z.string().nullish(),
  required_studio: z.string().nullish(),
  expected: z.string().nullish(),
  actual: z.string().nullish(),
  projects: z.array(GitCredentialUsageSchema).nullish(),
  can_adopt: z.boolean().nullish(),
  paths: z.array(z.string()).nullish(),
  host_keys: z.array(GitHostKeySchema).nullish(),
  certificate: GitTlsCertificateSchema.nullish(), // tls_untrusted_ca
});

// --- операции -------------------------------------------------------------------

export const OperationWarningSchema = z.object({
  code: z.string(),
  paths: z.array(z.string()),
});

export const AutoMergedFileSchema = z.object({
  path: z.string(),
  action: z.string(),
  copy_path: z.string().nullish(),
});

export const ConflictCountsSchema = z.object({
  files_total: z.number(),
  files_open: z.number(),
});

export const SyncResultSchema = z.object({
  outcome: z.string(),
  pulled_commits: z.number(),
  pushed_commits: z.number(),
  merge_commit: z.string().nullish(),
  files_changed: z.number(),
  auto: z.array(AutoMergedFileSchema),
  conflicts: ConflictCountsSchema.nullish(),
  warnings: z.array(OperationWarningSchema),
});

export const CloneResultSchema = z.object({
  project_id: z.string(),
  folder: z.string(),
  access: z.string(),
  required_studio: z.string().nullish(),
  warnings: z.array(OperationWarningSchema),
});

export const OperationErrorSchema = z.object({
  code: z.string(),
  detail: z.string(),
});

// Результат — SyncResult или CloneResult: различаем по обязательным полям.
export const OperationSchema = z.object({
  id: z.string(),
  kind: z.string(),
  project_id: z.string().nullish(),
  status: z.string(),
  phase: z.string(),
  percent: z.number().nullish(),
  message: z.string().nullish(),
  cancellable: z.boolean(),
  started_at: z.string(),
  finished_at: z.string().nullish(),
  result: z.union([SyncResultSchema, CloneResultSchema]).nullish(),
  error: OperationErrorSchema.nullish(),
});

export const OperationStartedSchema = z.object({
  operation_id: z.string(),
});

// --- состояние проекта ----------------------------------------------------------

export const GitCommitBriefSchema = z.object({
  id: z.string(),
  short_id: z.string(),
  message: z.string(),
  author: z.string(),
  author_email: z.string().nullish(),
  created_at: z.string(),
  kind: z.string(),
});

export const GitRemoteInfoSchema = z.object({
  display_url: z.string(),
  kind: z.string(),
  host: z.string().nullish(),
  provider: z.string(),
  provider_info: GitProviderInfoSchema.nullish(),
  web_url: z.string().nullish(),
  branch: z.string(),
  local_branch: z.string(),
  credential: z
    .object({ id: z.string(), label: z.string(), kind: z.string() })
    .nullish(),
  insecure_http: z.boolean(),
});

export const GitStatusSchema = z.object({
  connected: z.boolean(),
  ui_state: z.string(),
  remote: GitRemoteInfoSchema.nullish(),
  relation: z.string(),
  ahead: z.number(),
  behind: z.number(),
  behind_files: z.number(),
  health: z.string(),
  last_error: z
    .object({ code: z.string(), detail: z.string(), at: z.string() })
    .nullish(),
  blocked: z
    .object({ reason: z.string(), required_studio: z.string().nullish() })
    .nullish(),
  profile_ok: z.boolean(),
  incoming: z.array(GitCommitBriefSchema),
  outgoing: z.array(GitCommitBriefSchema),
  operation: z
    .object({
      id: z.string(),
      kind: z.string(),
      phase: z.string(),
      percent: z.number().nullish(),
      cancellable: z.boolean(),
      started_at: z.string(),
    })
    .nullish(),
  pending: z
    .object({
      session_id: z.string(),
      files_total: z.number(),
      files_open: z.number(),
    })
    .nullish(),
  last_fetch_at: z.string().nullish(),
  last_fetch_ok_at: z.string().nullish(),
  last_sync_at: z.string().nullish(),
  last_sync: z
    .object({
      id: z.string(),
      at: z.string(),
      outcome: z.string(),
      pulled_commits: z.number(),
      pushed_commits: z.number(),
    })
    .nullish(),
  auto_fetch: z.object({
    enabled: z.boolean(),
    interval_s: z.number(),
    next_fetch_at: z.string().nullish(),
  }),
  shared_folder: z
    .object({
      provider: z.string(),
      root: z.string(),
      acknowledged: z.boolean(),
    })
    .nullish(),
  bot_authored_commits: z.number(),
});

export const ConnectRemoteRequestSchema = z.object({
  url: z.string(),
  credential_id: z.string().nullable(),
  branch: z.string().nullish(),
  remote_branch: z.string().nullish(),
  adopt: z.string().nullish(),
  insecure_http: z.boolean().nullish(),
});

export const UpdateGitSettingsRequestSchema = z.object({
  auto_fetch: z.boolean().nullish(),
  interval_s: z.number().nullish(),
  shared_folder_ack: z.boolean().nullish(),
});

export const GitContentsSchema = z.object({
  files: z.number(),
  bytes: z.number(),
  commits: z.number(),
  bot_authored_commits: z.number(),
  signatures: z.number(),
  nda_files: z.number(),
  pdf_tracked: z.boolean(),
  largest: z.array(z.object({ path: z.string(), bytes: z.number() })),
  over_limit: z.array(
    z.object({ path: z.string(), bytes: z.number(), limit: z.number() }),
  ),
  lfs_pointers: z.number(),
});

// --- конфликты ------------------------------------------------------------------

export const ConflictSideSchema = z.object({
  commit: z.string(),
  author: z.string().nullish(),
  at: z.string().nullish(),
  message: z.string().nullish(),
});

export const ConflictFileSideSchema = z.object({
  exists: z.boolean(),
  size: z.number().nullish(),
  author: z.string().nullish(),
  at: z.string().nullish(),
});

export const HunkChoiceSchema = z.object({
  choice: z.string(), // mine | theirs | both | both_reverse | base | custom
  text: z.string().nullish(),
});

export const FieldChoiceSchema = z.object({
  choice: z.string(), // mine | theirs | union
});

export const FileResolutionSchema = z.discriminatedUnion("kind", [
  z.object({ kind: z.literal("file"), choice: z.string() }),
  z.object({
    kind: z.literal("hunks"),
    hunks: z.record(z.string(), HunkChoiceSchema),
  }),
  z.object({
    kind: z.literal("fields"),
    fields: z.record(z.string(), FieldChoiceSchema),
  }),
  z.object({ kind: z.literal("text"), content: z.string() }),
]);

export const ConflictFileSchema = z.object({
  path: z.string(),
  owner: z.string().nullish(),
  kind: z.string(), // text | json | binary
  action: z.string(),
  conflict_type: z.string().nullish(),
  hunks: z.number(),
  open_hunks: z.number(),
  fields: z.number(),
  open_fields: z.number(),
  resolved: z.boolean(),
  resolution: FileResolutionSchema.nullish(),
  allowed: z.array(z.string()), // mine | theirs | newest
  default_resolution: z.string().nullish(),
  sides: z.object({
    ours: ConflictFileSideSchema,
    theirs: ConflictFileSideSchema,
    base: ConflictFileSideSchema,
  }),
  copy_path: z.string().nullish(),
  doc_id: z.string().nullish(),
});

export const ConflictSessionSchema = z.object({
  id: z.string(),
  fingerprint: z.string(),
  ours: ConflictSideSchema,
  theirs: ConflictSideSchema,
  base: ConflictSideSchema.nullish(),
  counts: z.object({
    conflict: z.number(),
    auto: z.number(),
    total: z.number(),
  }),
  unresolved: z.number(),
  drafts_saved_at: z.string().nullish(),
  warnings: z.array(OperationWarningSchema),
  files: z.array(ConflictFileSchema),
});

export const TextSegmentSchema = z.discriminatedUnion("type", [
  z.object({ type: z.literal("clean"), lines: z.array(z.string()) }),
  z.object({
    type: z.literal("hunk"),
    key: z.string(),
    ours: z.array(z.string()),
    base: z.array(z.string()),
    theirs: z.array(z.string()),
    ours_start: z.number(),
    result_start: z.number(),
  }),
]);

export const JsonFieldConflictSchema = z.object({
  pointer: z.string(),
  label: z.string().nullish(),
  type: z.string(), // scalar | list | record | presence
  base: z.json(),
  ours: z.json(),
  theirs: z.json(),
  allowed: z.array(z.string()), // mine | theirs | union
  status: z.string(), // auto | conflict
});

export const ConflictFileDetailSchema = z.discriminatedUnion("kind", [
  z.object({
    kind: z.literal("text"),
    eol: z.string(),
    truncated: z.boolean(),
    segments: z.array(TextSegmentSchema),
  }),
  z.object({
    kind: z.literal("json"),
    fields: z.array(JsonFieldConflictSchema),
  }),
  z.object({
    kind: z.literal("binary"),
    ours: ConflictFileSideSchema,
    theirs: ConflictFileSideSchema,
    newer: z.string(),
    copy_path: z.string().nullish(),
  }),
  z.object({ kind: z.literal("delete"), deleted_by: z.string() }),
]);

export const ConflictDiffSchema = z.object({
  path: z.string(),
  binary: z.boolean(),
  patch: z.string(),
  truncated: z.boolean(),
});

export const SaveConflictDraftRequestSchema = z.object({
  resolutions: z.record(z.string(), FileResolutionSchema),
});

export const ResolveConflictsRequestSchema = z.object({
  fingerprint: z.string(),
  resolutions: z.record(z.string(), FileResolutionSchema).nullish(),
  push: z.boolean(),
});

// --- CI -------------------------------------------------------------------------

export const CiRequestSchema = z.object({
  provider: z.string(), // github | gitlab
  docs: z.union([z.literal("all"), z.array(z.string())]),
  publish: z.string(), // artifacts | release
  triggers: z.array(z.string()), // push | tag | manual
  image: z.string().nullish(),
});

export const CiWriteRequestSchema = CiRequestSchema.extend({
  overwrite: z.boolean(),
});

export const CiPreviewSchema = z.object({
  files: z.array(
    z.object({
      path: z.string(),
      content: z.string(),
      exists: z.boolean(),
      same: z.boolean(),
    }),
  ),
  command: z.string(),
  notes: z.array(z.string()),
});

export const CiWriteSchema = z.object({
  written: z.array(z.string()),
});

// --- история --------------------------------------------------------------------

// Расширение VcsCommit: e-mail автора, признак слияния и метка отправки.
// Базовые поля коммита описаны в entities/vcs, здесь только добавки контракта.
export const HistoryCommitExtrasSchema = z.object({
  author_email: z.string().nullish(),
  is_merge: z.boolean(),
  sync: z.string().nullish(), // pushed | unpushed | incoming, без репозитория null
});

// Описание схемы живёт в entities/vcs: фильтры истории читают его оттуда.
export const HistoryFacetsSchema = VcsHistoryFacetsSchema;

export type GitHostKey = z.infer<typeof GitHostKeySchema>;
export type GitTlsCertificate = z.infer<typeof GitTlsCertificateSchema>;
export type GitProviderInfo = z.infer<typeof GitProviderInfoSchema>;
export type GitErrorBody = z.infer<typeof GitErrorBodySchema>;
export type OperationWarning = z.infer<typeof OperationWarningSchema>;
export type AutoMergedFile = z.infer<typeof AutoMergedFileSchema>;
export type SyncResult = z.infer<typeof SyncResultSchema>;
export type CloneResult = z.infer<typeof CloneResultSchema>;
export type GitOperation = z.infer<typeof OperationSchema>;
export type OperationStarted = z.infer<typeof OperationStartedSchema>;
export type GitCommitBrief = z.infer<typeof GitCommitBriefSchema>;
export type GitRemoteInfo = z.infer<typeof GitRemoteInfoSchema>;
export type GitStatus = z.infer<typeof GitStatusSchema>;
export type ConnectRemoteRequest = z.infer<typeof ConnectRemoteRequestSchema>;
export type UpdateGitSettingsRequest = z.infer<
  typeof UpdateGitSettingsRequestSchema
>;
export type GitContents = z.infer<typeof GitContentsSchema>;
export type ConflictSide = z.infer<typeof ConflictSideSchema>;
export type ConflictFileSide = z.infer<typeof ConflictFileSideSchema>;
export type HunkChoice = z.infer<typeof HunkChoiceSchema>;
export type FieldChoice = z.infer<typeof FieldChoiceSchema>;
export type FileResolution = z.infer<typeof FileResolutionSchema>;
export type ConflictFile = z.infer<typeof ConflictFileSchema>;
export type ConflictSession = z.infer<typeof ConflictSessionSchema>;
export type TextSegment = z.infer<typeof TextSegmentSchema>;
export type JsonFieldConflict = z.infer<typeof JsonFieldConflictSchema>;
export type ConflictFileDetail = z.infer<typeof ConflictFileDetailSchema>;
export type ConflictDiff = z.infer<typeof ConflictDiffSchema>;
export type SaveConflictDraftRequest = z.infer<
  typeof SaveConflictDraftRequestSchema
>;
export type ResolveConflictsRequest = z.infer<
  typeof ResolveConflictsRequestSchema
>;
export type CiRequest = z.infer<typeof CiRequestSchema>;
export type CiWriteRequest = z.infer<typeof CiWriteRequestSchema>;
export type CiPreview = z.infer<typeof CiPreviewSchema>;
export type CiWrite = z.infer<typeof CiWriteSchema>;
export type HistoryCommitExtras = z.infer<typeof HistoryCommitExtrasSchema>;
export type HistoryFacets = z.infer<typeof HistoryFacetsSchema>;
