import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import type { UpdateSettingsRequest } from "@shared/api/types";
import { settingsApi, type SettingsData } from "./settingsApi";

export const settingsKeys = {
  all: ["settings"] as const,
  current: () => [...settingsKeys.all, "current"] as const,
};

export const useAppSettings = () =>
  useQuery<SettingsData>({
    queryKey: settingsKeys.current(),
    queryFn: () => settingsApi.get(),
  });

export const useUpdateAppSettings = () => {
  const queryClient = useQueryClient();
  return useMutation<SettingsData, Error, UpdateSettingsRequest>({
    mutationFn: (body) => settingsApi.update(body),
    onSuccess: (data) => {
      queryClient.setQueryData(settingsKeys.current(), data);
    },
  });
};
