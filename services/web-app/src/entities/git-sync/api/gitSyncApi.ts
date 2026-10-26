import { ApiError, apiClient, parseResp } from "@shared/api";
import {
  ConflictDiffSchema,
  ConflictFileDetailSchema,
  ConflictSessionSchema,
  GitContentsSchema,
  GitErrorBodySchema,
  GitStatusSchema,
  OperationSchema,
  OperationStartedSchema,
  type ConnectRemoteRequest,
  type FileResolution,
  type GitErrorBody,
  type GitStatus,
  type ResolveConflictsRequest,
  type UpdateGitSettingsRequest,
} from "./gitSyncSchemas";

// Состояние, как его видит интерфейс: контрактный GitStatus плюс признак, что
// бэкенд вообще умеет синхронизацию. Старый бэкенд отвечает 404 на GET /git:
// тогда это обычное «нет репозитория», а кнопку синхронизации прячем.
export type SyncStatusView = GitStatus & { supported: boolean };

export const NO_REMOTE_STATUS: GitStatus = {
  connected: false,
  ui_state: "no_remote",
  remote: null,
  relation: "none",
  ahead: 0,
  behind: 0,
  behind_files: 0,
  health: "ok",
  last_error: null,
  blocked: null,
  profile_ok: true,
  incoming: [],
  outgoing: [],
  operation: null,
  pending: null,
  last_fetch_at: null,
  last_fetch_ok_at: null,
  last_sync_at: null,
  last_sync: null,
  auto_fetch: { enabled: false, interval_s: 0, next_fetch_at: null },
  shared_folder: null,
  bot_authored_commits: 0,
};

export const toStatusView = (
  status: GitStatus,
  supported = true,
): SyncStatusView => ({ ...status, supported });

// view: ours — моя версия, theirs — чужая, result — итог с учётом черновика.
export type ConflictDiffView = "ours" | "theirs" | "result";
export type ConflictBlobSide = "ours" | "theirs" | "base";

export type ConnectRemoteParams = ConnectRemoteRequest;

// Разбирает ошибку Git-синхронизации: плоское тело {detail, code, ...доп. поля}
// после перехватчика лежит в ApiError (detail, code, data). Возвращает типизированное
// тело либо null, если это не ошибка такого вида (сеть, чужой формат).
export const readGitError = (error: unknown): GitErrorBody | null => {
  if (!(error instanceof ApiError)) return null;
  const parsed = GitErrorBodySchema.safeParse({
    ...(error.data ?? {}),
    detail: error.detail,
    code: error.code,
  });
  return parsed.success ? parsed.data : null;
};

export type ExportBundleResult = {
  blob: Blob;
  filename: string;
};

export type ResolveConflictsParams = Omit<
  ResolveConflictsRequest,
  "push" | "resolutions"
> & {
  // null — взять сохранённые черновики на сервере.
  resolutions?: Record<string, FileResolution> | null;
  push?: boolean;
};

const gitPath = (projectId: string): string => `/projects/${projectId}/git`;

const filenameFromDisposition = (header: unknown): string | null => {
  if (typeof header !== "string") return null;
  const encoded = /filename\*=UTF-8''([^;]+)/i.exec(header);
  if (encoded?.[1]) {
    try {
      return decodeURIComponent(encoded[1]);
    } catch {
      return encoded[1];
    }
  }
  const plain = /filename="?([^";]+)"?/i.exec(header);
  return plain?.[1] ?? null;
};

export const gitSyncApi = {
  // Опрос состояния: ошибки не показываем тостом, их отражает сам элемент.
  getStatus: async (projectId: string): Promise<SyncStatusView> => {
    try {
      const status = await apiClient
        .get(gitPath(projectId), { silentError: true })
        .then(parseResp(GitStatusSchema));
      return toStatusView(status);
    } catch (error) {
      if (error instanceof ApiError && error.status === 404) {
        return toStatusView(NO_REMOTE_STATUS, false);
      }
      throw error;
    }
  },

  fetchRemote: (projectId: string) =>
    apiClient
      .post(`${gitPath(projectId)}/fetch`, undefined, {
        silentError: true,
        timeout: 120_000,
      })
      .then(parseResp(GitStatusSchema)),

  connectRemote: (projectId: string, params: ConnectRemoteParams) =>
    apiClient
      .put(`${gitPath(projectId)}/remote`, params, {
        // Адрес может нести токен, а коды ошибок разбирает окно подключения.
        silentError: true,
        timeout: 120_000,
      })
      .then(parseResp(GitStatusSchema)),

  disconnectRemote: (
    projectId: string,
    forgetCredential = false,
  ): Promise<void> =>
    apiClient
      .delete(`${gitPath(projectId)}/remote`, {
        params: { forget_credential: forgetCredential },
        // Причину сбоя показывает окно отключения, второй тост не нужен.
        silentError: true,
      })
      .then(() => undefined),

  updateSettings: (projectId: string, params: UpdateGitSettingsRequest) =>
    apiClient
      .patch(`${gitPath(projectId)}/settings`, params)
      .then(parseResp(GitStatusSchema)),

  getContents: (projectId: string) =>
    apiClient
      .get(`${gitPath(projectId)}/contents`)
      .then(parseResp(GitContentsSchema)),

  startSync: (projectId: string) =>
    apiClient
      .post(`${gitPath(projectId)}/sync`, {}, { silentError: true })
      .then(parseResp(OperationStartedSchema)),

  getOperation: (operationId: string) =>
    apiClient
      .get(`/git/operations/${operationId}`, { silentError: true })
      .then(parseResp(OperationSchema)),

  cancelOperation: (operationId: string) =>
    apiClient
      .post(`/git/operations/${operationId}/cancel`, undefined, {
        silentError: true,
      })
      .then(parseResp(OperationSchema)),

  // --- конфликты ---------------------------------------------------------------

  getConflicts: (projectId: string) =>
    apiClient
      .get(`${gitPath(projectId)}/conflicts`, { silentError: true })
      .then(parseResp(ConflictSessionSchema)),

  getConflictFile: (projectId: string, path: string) =>
    apiClient
      .get(`${gitPath(projectId)}/conflicts/file`, { params: { path } })
      .then(parseResp(ConflictFileDetailSchema)),

  getConflictDiff: (projectId: string, path: string, view: ConflictDiffView) =>
    apiClient
      .get(`${gitPath(projectId)}/conflicts/diff`, { params: { path, view } })
      .then(parseResp(ConflictDiffSchema)),

  getConflictBlob: (
    projectId: string,
    path: string,
    side: ConflictBlobSide,
  ): Promise<Blob> =>
    apiClient
      .get(`${gitPath(projectId)}/conflicts/blob`, {
        params: { path, side },
        responseType: "blob",
      })
      .then((r) => r.data as Blob),

  saveConflictDraft: (
    projectId: string,
    resolutions: Record<string, FileResolution>,
  ): Promise<void> =>
    apiClient
      .put(
        `${gitPath(projectId)}/conflicts/draft`,
        { resolutions },
        // Черновик пишется молча: сбой виден по отметке «не сохранено».
        { silentError: true },
      )
      .then(() => undefined),

  resolveConflicts: (projectId: string, params: ResolveConflictsParams) =>
    apiClient
      .post(
        `${gitPath(projectId)}/conflicts/resolve`,
        {
          fingerprint: params.fingerprint,
          resolutions: params.resolutions ?? null,
          push: params.push ?? true,
        },
        // plan_outdated, unresolved_conflicts и прочее разбирает экран конфликтов.
        { silentError: true },
      )
      .then(parseResp(OperationStartedSchema)),

  abortConflicts: (projectId: string) =>
    apiClient
      .delete(`${gitPath(projectId)}/conflicts`)
      .then(parseResp(GitStatusSchema)),

  // --- переносной файл ---------------------------------------------------------

  exportBundle: async (
    projectId: string,
    password?: string,
  ): Promise<ExportBundleResult> => {
    const response = await apiClient.post(
      `${gitPath(projectId)}/bundle/export`,
      password ? { password } : {},
      { responseType: "blob", silentError: true, timeout: 300_000 },
    );
    const headers = response.headers as Record<string, unknown>;
    return {
      blob: response.data as Blob,
      filename:
        filenameFromDisposition(headers["content-disposition"]) ??
        "project.bundle",
    };
  },

  importBundle: (projectId: string, file: File, password?: string) => {
    const formData = new FormData();
    formData.append("file", file);
    if (password) formData.append("password", password);
    return apiClient
      .post(`${gitPath(projectId)}/bundle/import`, formData, {
        // Границу multipart выставляет браузер: иначе сервер не разберёт тело.
        headers: { "Content-Type": null },
        silentError: true,
        timeout: 300_000,
      })
      .then(parseResp(OperationStartedSchema));
  },
};
