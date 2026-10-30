import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  myRunnersApi,
  projectBuildRunnersApi,
  remoteRunnerApi,
} from "./runnerApi";
import type {
  BuildRunnersPolicy,
  CreateMyRunnerTokenRequest,
  RemoteRunnerStatus,
  RunnerPairingDecision,
  UpdateMyRunnerRequest,
  UpdateRemoteRunnerRequest,
} from "../model/runner.schema";

export const runnerKeys = {
  all: ["runners"] as const,
  mine: () => [...runnerKeys.all, "mine"] as const,
  tokens: () => [...runnerKeys.all, "tokens"] as const,
  pairing: (code: string) => [...runnerKeys.all, "pairing", code] as const,
  project: (projectId: string) =>
    [...runnerKeys.all, "project", projectId] as const,
  remote: () => [...runnerKeys.all, "remote"] as const,
};

// Пока открыт диалог подключения, список опрашивается чаще: новый раннер
// появляется сам, без перезагрузки страницы.
export const CONNECT_POLL_MS = 5_000;
const LIST_POLL_MS = 30_000;

export const useMyRunners = (options: { fastPoll?: boolean } = {}) =>
  useQuery({
    queryKey: runnerKeys.mine(),
    queryFn: () => myRunnersApi.list(),
    staleTime: 10_000,
    refetchInterval: options.fastPoll ? CONNECT_POLL_MS : LIST_POLL_MS,
  });

export const useMyRunnerTokens = () =>
  useQuery({
    queryKey: runnerKeys.tokens(),
    queryFn: () => myRunnersApi.tokens(),
    staleTime: 30_000,
  });

const useInvalidateMine = () => {
  const client = useQueryClient();
  return () => {
    void client.invalidateQueries({ queryKey: runnerKeys.all });
  };
};

export const useUpdateMyRunner = () => {
  const invalidate = useInvalidateMine();
  return useMutation({
    mutationFn: ({ id, body }: { id: string; body: UpdateMyRunnerRequest }) =>
      myRunnersApi.update(id, body),
    onSuccess: invalidate,
  });
};

export const useRotateMyRunner = () => {
  const invalidate = useInvalidateMine();
  return useMutation({
    mutationFn: (id: string) => myRunnersApi.rotate(id),
    onSuccess: invalidate,
  });
};

export const useRevokeMyRunner = () => {
  const invalidate = useInvalidateMine();
  return useMutation({
    mutationFn: (id: string) => myRunnersApi.revoke(id),
    onSuccess: invalidate,
  });
};

export const useCreateMyRunnerToken = () => {
  const invalidate = useInvalidateMine();
  return useMutation({
    mutationFn: (body: CreateMyRunnerTokenRequest) =>
      myRunnersApi.createToken(body),
    onSuccess: invalidate,
  });
};

export const useRevokeMyRunnerToken = () => {
  const invalidate = useInvalidateMine();
  return useMutation({
    mutationFn: (id: string) => myRunnersApi.revokeToken(id),
    onSuccess: invalidate,
  });
};

/** Сведения о коде сопряжения. Без повторов: неверный код не должен жечь лимит частоты. */
export const useRunnerPairing = (code: string | null) =>
  useQuery({
    queryKey: runnerKeys.pairing(code ?? ""),
    queryFn: () => myRunnersApi.pairing(code ?? ""),
    enabled: code !== null,
    retry: false,
    staleTime: Infinity,
  });

export const useDecideRunnerPairing = () => {
  const client = useQueryClient();
  return useMutation({
    mutationFn: ({
      code,
      decision,
    }: {
      code: string;
      decision: RunnerPairingDecision;
    }) => myRunnersApi.decidePairing(code, decision),
    onSuccess: (info, { code }) => {
      client.setQueryData(runnerKeys.pairing(code), info);
      void client.invalidateQueries({ queryKey: runnerKeys.mine() });
    },
  });
};

export const useProjectBuildRunners = (projectId: string) =>
  useQuery({
    queryKey: runnerKeys.project(projectId),
    queryFn: () => projectBuildRunnersApi.get(projectId),
    staleTime: 30_000,
  });

export const useUpdateProjectBuildRunners = (projectId: string) => {
  const client = useQueryClient();
  return useMutation({
    mutationFn: (policy: BuildRunnersPolicy) =>
      projectBuildRunnersApi.update(projectId, policy),
    onSuccess: (data) => {
      client.setQueryData(runnerKeys.project(projectId), data);
    },
  });
};

// Пока Студия подключается или ждёт код, состояние меняется само: опрашиваем часто.
const REMOTE_FAST_MS = 2_000;
const REMOTE_SLOW_MS = 15_000;
const BUSY_REMOTE: readonly RemoteRunnerStatus["state"][] = [
  "pairing",
  "connecting",
  "offline",
];

export const useRemoteRunner = (enabled = true) =>
  useQuery({
    queryKey: runnerKeys.remote(),
    queryFn: () => remoteRunnerApi.status(),
    enabled,
    refetchInterval: (query) =>
      query.state.data && BUSY_REMOTE.includes(query.state.data.state)
        ? REMOTE_FAST_MS
        : REMOTE_SLOW_MS,
  });

const useSetRemote = () => {
  const client = useQueryClient();
  return (data: RemoteRunnerStatus) => {
    client.setQueryData(runnerKeys.remote(), data);
  };
};

export const useUpdateRemoteRunner = () => {
  const set = useSetRemote();
  return useMutation({
    mutationFn: (body: UpdateRemoteRunnerRequest) =>
      remoteRunnerApi.update(body),
    onSuccess: set,
  });
};

export const usePairRemoteRunner = () => {
  const set = useSetRemote();
  return useMutation({
    mutationFn: ({ serverUrl, name }: { serverUrl: string; name: string }) =>
      remoteRunnerApi.pair(serverUrl, name),
    onSuccess: set,
  });
};

export const useRemoteRunnerToken = () => {
  const set = useSetRemote();
  return useMutation({
    mutationFn: ({ serverUrl, token }: { serverUrl: string; token: string }) =>
      remoteRunnerApi.useToken(serverUrl, token),
    onSuccess: set,
  });
};

export const useCancelRemotePairing = () => {
  const set = useSetRemote();
  return useMutation({
    mutationFn: () => remoteRunnerApi.cancelPairing(),
    onSuccess: set,
  });
};

export const useUnpairRemoteRunner = () => {
  const set = useSetRemote();
  return useMutation({
    mutationFn: () => remoteRunnerApi.unpair(),
    onSuccess: set,
  });
};
