import {
  useMutation,
  useQuery,
  useQueryClient,
  type QueryClient,
} from "@tanstack/react-query";
import { documentKeys } from "@entities/document";
import { formKeys } from "@entities/form";
import { projectKeys } from "@entities/project";
import { signatureKeys } from "@entities/signature";
import { templateUpdateKeys } from "@entities/template-update";
import { vcsKeys } from "@entities/vcs";
import {
  gitSyncApi,
  toStatusView,
  type ConflictBlobSide,
  type ConflictDiffView,
  type ConnectRemoteParams,
  type ResolveConflictsParams,
  type SyncStatusView,
} from "./gitSyncApi";
import type {
  FileResolution,
  GitOperation,
  GitStatus,
  UpdateGitSettingsRequest,
} from "./gitSyncSchemas";

// Опрос состояния: редко, пока ничего не происходит, и раз в секунду, пока идёт
// операция. Сам опрос читает локальные файлы бэкенда и в сеть не ходит.
export const SYNC_STATUS_IDLE_POLL_MS = 30_000;
export const SYNC_STATUS_ACTIVE_POLL_MS = 1_000;
export const SYNC_STATUS_STALE_MS = 5_000;

export const gitSyncKeys = {
  all: ["git-sync"] as const,
  project: (projectId: string) => [...gitSyncKeys.all, projectId] as const,
  status: (projectId: string) =>
    [...gitSyncKeys.project(projectId), "status"] as const,
  contents: (projectId: string) =>
    [...gitSyncKeys.project(projectId), "contents"] as const,
  conflicts: (projectId: string) =>
    [...gitSyncKeys.project(projectId), "conflicts"] as const,
  conflictFile: (projectId: string, path: string) =>
    [...gitSyncKeys.conflicts(projectId), "file", path] as const,
  conflictDiff: (
    projectId: string,
    path: string,
    view: ConflictDiffView,
    revision: string,
  ) =>
    [
      ...gitSyncKeys.conflicts(projectId),
      "diff",
      path,
      view,
      revision,
    ] as const,
  conflictBlob: (projectId: string, path: string, side: ConflictBlobSide) =>
    [...gitSyncKeys.conflicts(projectId), "blob", path, side] as const,
  operations: () => [...gitSyncKeys.all, "operation"] as const,
  operation: (operationId: string) =>
    [...gitSyncKeys.operations(), operationId] as const,
};

// Решение, нужен ли опрос: без репозитория ничего не меняется само, а старый
// бэкенд без синхронизации опрашивать незачем.
export const syncStatusRefetchInterval = (
  status: SyncStatusView | undefined,
): number | false => {
  if (!status?.supported) return false;
  if (status.operation) return SYNC_STATUS_ACTIVE_POLL_MS;
  return status.connected ? SYNC_STATUS_IDLE_POLL_MS : false;
};

export const useSyncStatus = (projectId: string) =>
  useQuery({
    queryKey: gitSyncKeys.status(projectId),
    queryFn: () => gitSyncApi.getStatus(projectId),
    enabled: !!projectId,
    staleTime: SYNC_STATUS_STALE_MS,
    refetchInterval: (query) => syncStatusRefetchInterval(query.state.data),
    // Фоновая вкладка не опрашивает: при возвращении сработает refetchOnWindowFocus.
    refetchIntervalInBackground: false,
    refetchOnWindowFocus: true,
    retry: false,
  });

// Что сделать после синхронизации: слияние меняет файлы, журнал версий, lock,
// подписи и формы. По образцу обновления шаблона, плюс собственные ключи.
export const invalidateAfterSync = (
  queryClient: QueryClient,
  projectId: string,
): void => {
  void queryClient.invalidateQueries({ queryKey: gitSyncKeys.all });
  void queryClient.invalidateQueries({ queryKey: vcsKeys.all });
  void queryClient.invalidateQueries({
    queryKey: projectKeys.detail(projectId),
  });
  void queryClient.invalidateQueries({ queryKey: documentKeys.all });
  void queryClient.invalidateQueries({ queryKey: ["files"] });
  void queryClient.invalidateQueries({ queryKey: templateUpdateKeys.all });
  void queryClient.invalidateQueries({ queryKey: formKeys.all });
  void queryClient.invalidateQueries({ queryKey: signatureKeys.all });
};

const setStatus = (
  queryClient: QueryClient,
  projectId: string,
  status: GitStatus,
): void => {
  queryClient.setQueryData(gitSyncKeys.status(projectId), toStatusView(status));
};

// Фоновое обновление сведений об удалённом репозитории. Ошибки молчат: их
// отражает состояние (нет сети, отказ входа), а не тосты.
export const useFetchRemote = () => {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (projectId: string) => gitSyncApi.fetchRemote(projectId),
    onSuccess: (status, projectId) => {
      setStatus(queryClient, projectId, status);
    },
    onError: (_error, projectId) => {
      // Причину сбоя сервер записал в состояние: перечитываем его.
      void queryClient.invalidateQueries({
        queryKey: gitSyncKeys.status(projectId),
      });
    },
  });
};

export const useStartSync = () => {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (projectId: string) => gitSyncApi.startSync(projectId),
    onSettled: (_data, _error, projectId) => {
      // В состоянии теперь есть операция: опрос ускорится сам.
      void queryClient.invalidateQueries({
        queryKey: gitSyncKeys.status(projectId),
      });
    },
  });
};

const isFinished = (operation: GitOperation | undefined): boolean =>
  operation !== undefined && operation.status !== "running";

export const useOperation = (operationId: string | null | undefined) =>
  useQuery({
    queryKey: gitSyncKeys.operation(operationId ?? ""),
    queryFn: () => gitSyncApi.getOperation(operationId ?? ""),
    enabled: !!operationId,
    staleTime: 0,
    refetchInterval: (query) =>
      isFinished(query.state.data) ? false : SYNC_STATUS_ACTIVE_POLL_MS,
    retry: false,
  });

export const useCancelOperation = () => {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (operationId: string) =>
      gitSyncApi.cancelOperation(operationId),
    onSuccess: (operation) => {
      queryClient.setQueryData(gitSyncKeys.operation(operation.id), operation);
      void queryClient.invalidateQueries({ queryKey: gitSyncKeys.all });
    },
  });
};

export const useConnectRemote = () => {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({
      projectId,
      params,
    }: {
      projectId: string;
      params: ConnectRemoteParams;
    }) => gitSyncApi.connectRemote(projectId, params),
    onSuccess: (status, { projectId }) => {
      setStatus(queryClient, projectId, status);
      // Метки «отправлено» в истории зависят от репозитория.
      void queryClient.invalidateQueries({ queryKey: vcsKeys.all });
    },
  });
};

export const useDisconnectRemote = () => {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({
      projectId,
      forgetCredential,
    }: {
      projectId: string;
      forgetCredential?: boolean;
    }) => gitSyncApi.disconnectRemote(projectId, forgetCredential ?? false),
    onSuccess: (_, { projectId }) => {
      void queryClient.invalidateQueries({
        queryKey: gitSyncKeys.project(projectId),
      });
      void queryClient.invalidateQueries({ queryKey: vcsKeys.all });
    },
  });
};

export const useUpdateGitSettings = () => {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({
      projectId,
      params,
    }: {
      projectId: string;
      params: UpdateGitSettingsRequest;
    }) => gitSyncApi.updateSettings(projectId, params),
    onSuccess: (status, { projectId }) => {
      setStatus(queryClient, projectId, status);
    },
  });
};

// Что уйдёт в репозиторий: считается локально, в сеть не ходит.
export const useGitContents = (projectId: string, enabled = true) =>
  useQuery({
    queryKey: gitSyncKeys.contents(projectId),
    queryFn: () => gitSyncApi.getContents(projectId),
    enabled: !!projectId && enabled,
    staleTime: 0,
  });

// --- конфликты --------------------------------------------------------------------

// Сессия — снимок слияния на сервере; устареть может только по 409 plan_outdated.
export const useConflictSession = (projectId: string, enabled = true) =>
  useQuery({
    queryKey: gitSyncKeys.conflicts(projectId),
    queryFn: () => gitSyncApi.getConflicts(projectId),
    enabled: !!projectId && enabled,
    staleTime: 0,
    retry: false,
  });

export const useConflictFile = (projectId: string, path: string | null) =>
  useQuery({
    queryKey: gitSyncKeys.conflictFile(projectId, path ?? ""),
    queryFn: () => gitSyncApi.getConflictFile(projectId, path ?? ""),
    enabled: !!projectId && path !== null,
    staleTime: 0,
  });

// revision — отметка сохранённого черновика: итог (result) зависит от него.
export const useConflictDiff = (
  projectId: string,
  path: string | null,
  view: ConflictDiffView,
  revision: string | null = null,
) =>
  useQuery({
    queryKey: gitSyncKeys.conflictDiff(
      projectId,
      path ?? "",
      view,
      revision ?? "",
    ),
    queryFn: () => gitSyncApi.getConflictDiff(projectId, path ?? "", view),
    enabled: !!projectId && path !== null,
    staleTime: 0,
  });

const blobToDataUrl = (blob: Blob): Promise<string> =>
  new Promise((resolve, reject) => {
    const reader = new FileReader();
    reader.onload = () => {
      resolve(typeof reader.result === "string" ? reader.result : "");
    };
    reader.onerror = () => {
      reject(reader.error ?? new Error("cannot read the file"));
    };
    reader.readAsDataURL(blob);
  });

// Адрес для <img>: содержимое файла приходит запросом (так работает и без
// сервера), а адрес вида data: не нужно освобождать, как object URL.
export const useConflictBlobUrl = (
  projectId: string,
  path: string | null,
  side: ConflictBlobSide,
) => {
  const query = useQuery({
    queryKey: gitSyncKeys.conflictBlob(projectId, path ?? "", side),
    queryFn: async () =>
      blobToDataUrl(
        await gitSyncApi.getConflictBlob(projectId, path ?? "", side),
      ),
    enabled: !!projectId && path !== null,
    staleTime: 0,
    gcTime: 0,
  });
  return {
    url: query.data ?? null,
    isLoading: query.isLoading,
    isError: query.isError,
  };
};

export const useSaveConflictDraft = () => {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({
      projectId,
      resolutions,
    }: {
      projectId: string;
      resolutions: Record<string, FileResolution>;
    }) => gitSyncApi.saveConflictDraft(projectId, resolutions),
    onSuccess: (_, { projectId }) => {
      // Счётчики открытых мест и итоговый diff зависят от черновика.
      void queryClient.invalidateQueries({
        queryKey: gitSyncKeys.conflicts(projectId),
      });
    },
  });
};

export const useResolveConflicts = () => {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({
      projectId,
      params,
    }: {
      projectId: string;
      params: ResolveConflictsParams;
    }) => gitSyncApi.resolveConflicts(projectId, params),
    onSuccess: (_, { projectId }) => {
      void queryClient.invalidateQueries({
        queryKey: gitSyncKeys.status(projectId),
      });
    },
  });
};

export const useAbortConflicts = () => {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (projectId: string) => gitSyncApi.abortConflicts(projectId),
    onSuccess: (status, projectId) => {
      setStatus(queryClient, projectId, status);
      queryClient.removeQueries({ queryKey: gitSyncKeys.conflicts(projectId) });
    },
  });
};

// --- переносной файл --------------------------------------------------------------

export const useExportBundle = () =>
  useMutation({
    mutationFn: ({
      projectId,
      password,
    }: {
      projectId: string;
      password?: string;
    }) => gitSyncApi.exportBundle(projectId, password),
  });

export const useImportBundle = () => {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({
      projectId,
      file,
      password,
    }: {
      projectId: string;
      file: File;
      password?: string;
    }) => gitSyncApi.importBundle(projectId, file, password),
    onSettled: (_data, _error, { projectId }) => {
      void queryClient.invalidateQueries({
        queryKey: gitSyncKeys.status(projectId),
      });
    },
  });
};
