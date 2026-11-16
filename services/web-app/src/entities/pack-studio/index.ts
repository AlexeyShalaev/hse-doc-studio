export * from "./api/schemas";
export {
  PACK_STUDIO_ERROR_CODES,
  isPackStudioErrorCode,
} from "./api/errorCodes";
export type { PackStudioErrorCode } from "./api/errorCodes";
export {
  packPreviewPdfUrl,
  packStudioApi,
  PackStaleFileError,
} from "./api/packStudioApi";
export type { PackFile, PackVersionRef } from "./api/packStudioApi";
// Вычислитель результата (docs/design/template-studio-outcome.md): схемы контракта и клиент
// эндпоинтов (outcomeApi, хуки). Сервер результата приходит срезами O1 и O2; до них клиент
// живёт на эталонах контракта (reference/, только разработка и тесты).
export * from "./api/outcome";
export { packOutcomeApi } from "./api/outcomeApi";
export type { OutcomeExplainReply } from "./api/outcomeApi";
export {
  busyDelaySeconds,
  isElementGone,
  isOutcomeBusy,
  normalizeExplainRequest,
  normalizeOutcomeRequest,
  packOutcomeKeys,
  retryOutcome,
  usePackOutcome,
  usePackOutcomeExplain,
  usePackOutcomeInputs,
  usePackScenarios,
} from "./api/outcomeQueries";
// Срез T14: файлы правил проверок и checks_version формой.
export {
  PackChecksConfigRequestSchema,
  PackChecksPatchRequestSchema,
  PackChecksSchema,
  packChecksApi,
  packChecksKeys,
  usePackChecksForm,
  usePatchPackChecksForm,
} from "./api/checks";
export type {
  PackCheckRule,
  PackChecks,
  PackChecksConfigRequest,
  PackChecksFile,
  PackChecksHeader,
  PackChecksOp,
  PackChecksPatchRequest,
} from "./api/checks";
// Срез T13: профили сдачи, пункты и порядок маршрута формой.
export {
  PackSubmissionPatchRequestSchema,
  PackSubmissionRoutesRequestSchema,
  PackSubmissionRoutesSchema,
  PackSubmissionSchema,
  packSubmissionApi,
  packSubmissionKeys,
  usePackSubmission,
  usePackSubmissionRoutes,
  usePatchPackSubmission,
} from "./api/submission";
export type {
  PackProfileHead,
  PackProfileRoute,
  PackSubmission,
  PackSubmissionExtra,
  PackSubmissionItem,
  PackSubmissionOp,
  PackSubmissionPatchRequest,
  PackSubmissionProfile,
  PackSubmissionRoutes,
  PackSubmissionRoutesRequest,
  PackSubmissionSlot,
  PackSubmissionWhen,
} from "./api/submission";
export {
  CI_APPROVAL_POLL_MS,
  CI_POLL_MS,
  PREVIEW_POLL_MS,
  WORKSPACE_POLL_MS,
  ciPollInterval,
  packStudioKeys,
  previewPollInterval,
  useAddPackServiceAccess,
  useCheckPackServiceAccess,
  useOpenPackOfficial,
  usePackOfficial,
  usePackOfficialAdmin,
  useCancelPackPreview,
  useCommitPack,
  useCreatePack,
  useCreatePackTemplate,
  useCreatePackVersion,
  usePackScaffoldOptions,
  useMovePackVersionEdits,
  usePackVersionOptions,
  usePackVersionState,
  useReleasePackVersion,
  useRenumberPackVersion,
  useSavePackVersionNotes,
  useMergePackBase,
  usePackChecks,
  usePackDiff,
  usePackGit,
  usePackPreviewBuild,
  usePackPreviewLog,
  usePackPreviewOptions,
  usePackServiceAccess,
  usePackDocLibrary,
  usePackSignatures,
  usePackVersionModel,
  usePatchPackSignatures,
  useProposePack,
  useRemovePackServiceAccess,
  useStartPackOver,
  useStartPackPreview,
  useSwitchPackBranch,
  useAddPackStudioGrant,
  useCreatePackWorkspace,
  useDeletePackWorkspace,
  usePackFile,
  usePackHints,
  usePackLint,
  usePackStudioAdmin,
  usePackStudioSection,
  usePackTree,
  usePackWorkspace,
  usePackWorkspaces,
  useRefreshPackWorkspace,
  useRemovePackStudioGrant,
  useSetPackStudioAdmin,
  useSetPackStudioSection,
} from "./api/queries";
export {
  ancestorsOf,
  buildFileTree,
  findVersion,
  findingTarget,
  isJinjaPath,
  isPackManifest,
  isTextPath,
  languageForPackPath,
  lintTargetOf,
  versionDirOf,
  packFormKind,
  versionRefOf,
} from "./lib/packPaths";
export type {
  PackFormKind,
  PackTreeNode,
  VersionLocation,
} from "./lib/packPaths";
export { packErrorText, workspaceErrorText } from "./lib/errorText";
export { PackErrorText } from "./ui/PackErrorText";
export {
  errorNumber,
  forkRequired,
  gitFailureHint,
  lintFailure,
  mergeConflictFiles,
} from "./lib/gitErrors";
export type { ForkRequired, LintFailure } from "./lib/gitErrors";
export {
  PACK_STUDIO_PATH,
  packFilesPath,
  packOutcomePath,
  packRulePath,
  packWorkspacePath,
  safeOutcomeBack,
} from "./lib/routes";
export type { RulePane } from "./lib/routes";
