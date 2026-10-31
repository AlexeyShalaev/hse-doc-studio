import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import type {
  DeviceDecisionRequest,
  GitServerLogin,
} from "../model/gitServer.schema";
import { deviceApi, gitServersApi, projectGitRemoteApi } from "./gitServerApi";

export const gitServerKeys = {
  all: ["git-server"] as const,
  device: (code: string) => ["git-server", "device", code] as const,
  projectRemote: (projectId: string) =>
    ["git-server", "project-remote", projectId] as const,
  servers: () => ["git-server", "servers"] as const,
  login: (loginId: string) => ["git-server", "login", loginId] as const,
  projects: (credentialId: string, q: string) =>
    ["git-server", "projects", credentialId, q] as const,
};

/** Опрос входа на сервер: пока ждём подтверждения, раз в 2 секунды. */
export const LOGIN_POLL_MS = 2000;

export const useDeviceAuthorization = (code: string | null) =>
  useQuery({
    queryKey: gitServerKeys.device(code ?? ""),
    queryFn: () => deviceApi.info(code ?? ""),
    enabled: code !== null,
    retry: false,
    staleTime: Infinity,
  });

export const useDecideDevice = () => {
  const client = useQueryClient();
  return useMutation({
    mutationFn: ({
      code,
      body,
    }: {
      code: string;
      body: DeviceDecisionRequest;
    }) => deviceApi.decide(code, body),
    onSuccess: (info, { code }) => {
      client.setQueryData(gitServerKeys.device(code), info);
    },
  });
};

export const useProjectGitRemote = (projectId: string, enabled = true) =>
  useQuery({
    queryKey: gitServerKeys.projectRemote(projectId),
    queryFn: () => projectGitRemoteApi.get(projectId),
    enabled,
    staleTime: 60_000,
  });

export const useGitServers = (enabled = true) =>
  useQuery({
    queryKey: gitServerKeys.servers(),
    queryFn: gitServersApi.list,
    enabled,
    staleTime: 15_000,
  });

export const useStartGitServerLogin = () =>
  useMutation({ mutationFn: gitServersApi.login });

export const useGitServerLogin = (loginId: string | null) => {
  const client = useQueryClient();
  return useQuery({
    queryKey: gitServerKeys.login(loginId ?? ""),
    queryFn: async (): Promise<GitServerLogin> => {
      const login = await gitServersApi.loginState(loginId ?? "");
      if (login.state === "approved") {
        void client.invalidateQueries({ queryKey: gitServerKeys.servers() });
      }
      return login;
    },
    enabled: loginId !== null,
    refetchInterval: (query) =>
      query.state.data?.state === "pending" || !query.state.data
        ? LOGIN_POLL_MS
        : false,
    retry: false,
  });
};

export const useCancelGitServerLogin = () =>
  useMutation({ mutationFn: gitServersApi.cancelLogin });

export const useGitServerProjects = (credentialId: string | null, q: string) =>
  useQuery({
    queryKey: gitServerKeys.projects(credentialId ?? "", q),
    queryFn: () => gitServersApi.projects(credentialId ?? "", q ? { q } : {}),
    enabled: credentialId !== null,
    retry: false,
  });

export const useForgetGitServer = () => {
  const client = useQueryClient();
  return useMutation({
    mutationFn: gitServersApi.forget,
    onSuccess: () => {
      void client.invalidateQueries({ queryKey: gitServerKeys.servers() });
    },
  });
};
