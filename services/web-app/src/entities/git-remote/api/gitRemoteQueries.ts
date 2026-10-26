import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { gitSyncKeys } from "@entities/git-sync";
import type { CiRequest, CiWriteRequest } from "@entities/git-sync";
import { gitRemoteApi, type CloneFromBundleParams } from "./gitRemoteApi";
import type {
  CloneRequest,
  CreateCredentialRequest,
  GitCredential,
  ProbeRequest,
  TrustHostRequest,
  UpdateCredentialRequest,
} from "./gitRemoteSchemas";

export const gitRemoteKeys = {
  all: ["git-remote"] as const,
  credentials: () => [...gitRemoteKeys.all, "credentials"] as const,
  hosts: () => [...gitRemoteKeys.all, "hosts"] as const,
  secrets: () => [...gitRemoteKeys.all, "secrets"] as const,
  sharedFolder: (folder: string) =>
    [...gitRemoteKeys.all, "shared-folder", folder] as const,
  cloneDefaults: (name: string) =>
    [...gitRemoteKeys.all, "clone-defaults", name] as const,
};

// --- доступы ----------------------------------------------------------------------

export const useCredentials = (enabled = true) =>
  useQuery({
    queryKey: gitRemoteKeys.credentials(),
    queryFn: () => gitRemoteApi.listCredentials(),
    enabled,
  });

export const useCreateCredential = () => {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (params: CreateCredentialRequest) =>
      gitRemoteApi.createCredential(params),
    onSuccess: (created) => {
      // Новый доступ виден в списке сразу, не дожидаясь перечитывания.
      queryClient.setQueryData<GitCredential[]>(
        gitRemoteKeys.credentials(),
        (list) => (list ? [...list, created] : list),
      );
      void queryClient.invalidateQueries({
        queryKey: gitRemoteKeys.credentials(),
      });
      void queryClient.invalidateQueries({ queryKey: gitRemoteKeys.secrets() });
    },
  });
};

export const useUpdateCredential = () => {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({
      id,
      params,
    }: {
      id: string;
      params: UpdateCredentialRequest;
    }) => gitRemoteApi.updateCredential(id, params),
    onSuccess: () => {
      void queryClient.invalidateQueries({
        queryKey: gitRemoteKeys.credentials(),
      });
      // Статус входа мог измениться: состояние проектов перечитывается.
      void queryClient.invalidateQueries({ queryKey: gitSyncKeys.all });
    },
  });
};

export const useDeleteCredential = () => {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({ id, force }: { id: string; force?: boolean }) =>
      gitRemoteApi.deleteCredential(id, force ?? false),
    onSuccess: () => {
      void queryClient.invalidateQueries({
        queryKey: gitRemoteKeys.credentials(),
      });
      void queryClient.invalidateQueries({ queryKey: gitRemoteKeys.secrets() });
      void queryClient.invalidateQueries({ queryKey: gitSyncKeys.all });
    },
  });
};

// --- ключи серверов ---------------------------------------------------------------

export const useGitHosts = (enabled = true) =>
  useQuery({
    queryKey: gitRemoteKeys.hosts(),
    queryFn: () => gitRemoteApi.listHosts(),
    enabled,
  });

export const useTrustHost = () => {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (params: TrustHostRequest) => gitRemoteApi.trustHost(params),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: gitRemoteKeys.hosts() });
      // Доверие меняет здоровье подключений: состояние проектов перечитывается.
      void queryClient.invalidateQueries({ queryKey: gitSyncKeys.all });
    },
  });
};

export const useDeleteHost = () => {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({ host, port }: { host: string; port?: number | null }) =>
      gitRemoteApi.deleteHost(host, port),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: gitRemoteKeys.hosts() });
    },
  });
};

export const useSecretsStatus = (enabled = true) =>
  useQuery({
    queryKey: gitRemoteKeys.secrets(),
    queryFn: () => gitRemoteApi.getSecretsStatus(),
    enabled,
  });

export const useSharedFolder = (folder: string, enabled = true) =>
  useQuery({
    queryKey: gitRemoteKeys.sharedFolder(folder),
    queryFn: () => gitRemoteApi.getSharedFolder(folder),
    enabled: enabled && folder.trim() !== "",
    staleTime: 60_000,
  });

// --- проверка адреса и клонирование -----------------------------------------------

// Результат проверки не кэшируем: это ответ на конкретный вопрос «что по этому
// адресу сейчас», а токен в ключе запроса был бы утечкой.
export const useProbe = () =>
  useMutation({
    mutationFn: (params: ProbeRequest) => gitRemoteApi.probe(params),
  });

export const useStartClone = () =>
  useMutation({
    mutationFn: (params: CloneRequest) => gitRemoteApi.startClone(params),
  });

export const useStartCloneFromBundle = () =>
  useMutation({
    mutationFn: (params: CloneFromBundleParams) =>
      gitRemoteApi.startCloneFromBundle(params),
  });

export const useCloneDefaults = (name: string, enabled = true) =>
  useQuery({
    queryKey: gitRemoteKeys.cloneDefaults(name),
    queryFn: () => gitRemoteApi.getCloneDefaults(name),
    enabled,
    staleTime: 60_000,
  });

// --- сборка в CI ------------------------------------------------------------------

export const useCiPreview = () =>
  useMutation({
    mutationFn: ({
      projectId,
      params,
    }: {
      projectId: string;
      params: CiRequest;
    }) => gitRemoteApi.previewCi(projectId, params),
  });

export const useWriteCi = () => {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({
      projectId,
      params,
    }: {
      projectId: string;
      params: CiWriteRequest;
    }) => gitRemoteApi.writeCi(projectId, params),
    onSuccess: (_, { projectId }) => {
      // Файлы CI появились в проекте и войдут в следующую отправку.
      void queryClient.invalidateQueries({ queryKey: ["files", projectId] });
      void queryClient.invalidateQueries({
        queryKey: gitSyncKeys.project(projectId),
      });
    },
  });
};
