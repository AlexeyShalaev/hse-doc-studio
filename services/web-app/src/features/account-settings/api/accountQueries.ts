import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { sessionKeys } from "@entities/session";
import { accountApi, type AccountPatch } from "./accountApi";

export const accountKeys = {
  all: ["account"] as const,
  profile: () => [...accountKeys.all, "profile"] as const,
  sessions: () => [...accountKeys.all, "sessions"] as const,
};

export const useAccount = () =>
  useQuery({
    queryKey: accountKeys.profile(),
    queryFn: () => accountApi.get(),
    staleTime: 60_000,
  });

export const useUpdateAccount = () => {
  const client = useQueryClient();
  return useMutation({
    mutationFn: (patch: AccountPatch) => accountApi.update(patch),
    onSuccess: (profile) => {
      client.setQueryData(accountKeys.profile(), profile);
      // Имя в меню аккаунта берётся из bootstrap.
      void client.invalidateQueries({ queryKey: sessionKeys.bootstrap() });
    },
  });
};

export const useChangePassword = () => {
  const client = useQueryClient();
  return useMutation({
    mutationFn: accountApi.changePassword,
    onSuccess: () =>
      client.invalidateQueries({ queryKey: accountKeys.sessions() }),
  });
};

export const useChangeEmail = () =>
  useMutation({ mutationFn: accountApi.changeEmail });

export const useAccountSessions = () =>
  useQuery({
    queryKey: accountKeys.sessions(),
    queryFn: () => accountApi.sessions(),
    staleTime: 15_000,
  });

export const useRevokeSession = () => {
  const client = useQueryClient();
  return useMutation({
    mutationFn: (id: string) => accountApi.revokeSession(id),
    onSuccess: () =>
      client.invalidateQueries({ queryKey: accountKeys.sessions() }),
  });
};

export const useRevokeOtherSessions = () => {
  const client = useQueryClient();
  return useMutation({
    mutationFn: () => accountApi.revokeOtherSessions(),
    onSuccess: () =>
      client.invalidateQueries({ queryKey: accountKeys.sessions() }),
  });
};
