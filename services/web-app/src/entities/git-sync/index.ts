export * from "./api/gitErrorCodes";
export * from "./api/gitSyncSchemas";
export {
  NO_REMOTE_STATUS,
  gitSyncApi,
  readGitError,
  toStatusView,
} from "./api/gitSyncApi";
export type {
  ConflictBlobSide,
  ConflictDiffView,
  ConnectRemoteParams,
  ExportBundleResult,
  ImportBundleOptions,
  ResolveConflictsParams,
  SyncStatusView,
} from "./api/gitSyncApi";
export {
  SYNC_STATUS_ACTIVE_POLL_MS,
  SYNC_STATUS_IDLE_POLL_MS,
  SYNC_STATUS_STALE_MS,
  gitSyncKeys,
  invalidateAfterSync,
  syncStatusRefetchInterval,
  useAbortConflicts,
  useCancelOperation,
  useConflictBlobUrl,
  useConflictDiff,
  useConflictFile,
  useConflictSession,
  useConnectRemote,
  useDisconnectRemote,
  useExportBundle,
  useFetchRemote,
  useGitContents,
  useImportBundle,
  useOperation,
  useResolveConflicts,
  useSaveConflictDraft,
  useStartSync,
  useSyncStatus,
  useUpdateGitSettings,
} from "./api/gitSyncQueries";
export { useSyncUiStore } from "./model/useSyncUiStore";
export type {
  ConnectDialogMode,
  SyncCommand,
  SyncCommandKind,
} from "./model/useSyncUiStore";
export {
  AUTHOR_PROFILE_PATH,
  CLONE_PATH,
  GIT_ACCESS_PATH,
  gitClonePath,
  gitConflictsPath,
  gitHistoryPath,
  gitSettingsPath,
  readCloneTarget,
} from "./model/syncPaths";
export type { CloneTarget } from "./model/syncPaths";
export { describeGitError, gitErrorMessage } from "./lib/gitErrorMessage";
