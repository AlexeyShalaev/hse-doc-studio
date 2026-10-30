import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { sessionKeys } from "@entities/session";
import type {
  SigningServerKeys,
  UpdateAdminBuildRequest,
  UpdateAdminInstanceRequest,
} from "@entities/session";
import { installApi } from "./installApi";

export const installKeys = {
  all: ["admin", "install"] as const,
  instance: () => [...installKeys.all, "instance"] as const,
  build: () => [...installKeys.all, "build"] as const,
  signing: () => [...installKeys.all, "signing"] as const,
};

export const useInstanceSettings = () =>
  useQuery({
    queryKey: installKeys.instance(),
    queryFn: () => installApi.instance(),
    staleTime: 0,
  });
export const useBuildSettings = () =>
  useQuery({
    queryKey: installKeys.build(),
    queryFn: () => installApi.build(),
    staleTime: 0,
  });
export const useSigningPolicy = () =>
  useQuery({
    queryKey: installKeys.signing(),
    queryFn: () => installApi.signing(),
    staleTime: 0,
  });

export const useUpdateInstance = () => {
  const client = useQueryClient();
  return useMutation({
    mutationFn: (body: UpdateAdminInstanceRequest) =>
      installApi.updateInstance(body),
    onSuccess: (data) => {
      client.setQueryData(installKeys.instance(), data);
    },
  });
};

export const useUpdateBuild = () => {
  const client = useQueryClient();
  return useMutation({
    mutationFn: (body: UpdateAdminBuildRequest) => installApi.updateBuild(body),
    onSuccess: (data) => {
      client.setQueryData(installKeys.build(), data);
    },
  });
};

/** Политика ключей меняет возможности пользователя: раздел «Подпись» читает их из bootstrap. */
export const useUpdateSigning = () => {
  const client = useQueryClient();
  return useMutation({
    mutationFn: (serverKeys: SigningServerKeys) =>
      installApi.updateSigning(serverKeys),
    onSuccess: (data) => {
      client.setQueryData(installKeys.signing(), data);
      void client.invalidateQueries({ queryKey: sessionKeys.bootstrap() });
    },
  });
};
