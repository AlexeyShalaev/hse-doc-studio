import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { gitSyncKeys } from "@entities/git-sync";
import { profileApi } from "./profileApi";
import type { Profile, ProfileRequest } from "./profileSchemas";

export const profileKeys = {
  all: ["profile"] as const,
  current: () => [...profileKeys.all, "current"] as const,
};

export const useProfile = () =>
  useQuery({
    queryKey: profileKeys.current(),
    queryFn: () => profileApi.get(),
    staleTime: 60_000,
  });

// Профиль влияет на то, чьим именем подписаны версии и можно ли подключать
// репозиторий (profile_required), поэтому состояние синхронизации перечитывается.
const applyProfile = (
  queryClient: ReturnType<typeof useQueryClient>,
  profile: Profile,
): void => {
  queryClient.setQueryData(profileKeys.current(), profile);
  void queryClient.invalidateQueries({ queryKey: gitSyncKeys.all });
};

export const useUpdateProfile = () => {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (params: ProfileRequest) => profileApi.update(params),
    onSuccess: (profile) => {
      applyProfile(queryClient, profile);
    },
  });
};

export const useClearProfile = () => {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: () => profileApi.clear(),
    onSuccess: (profile) => {
      applyProfile(queryClient, profile);
    },
  });
};
