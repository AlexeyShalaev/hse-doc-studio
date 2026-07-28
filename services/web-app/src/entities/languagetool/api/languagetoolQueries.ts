import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  languagetoolApi,
  type LanguageToolImagesList,
  type LanguageToolRemoteTags,
  type LanguageToolStatus,
  type SetActiveLanguageToolImage,
} from "./languagetoolApi";

export const languagetoolKeys = {
  all: ["languagetool"] as const,
  status: () => [...languagetoolKeys.all, "status"] as const,
  images: () => [...languagetoolKeys.all, "images"] as const,
  remoteTags: (repo: string) =>
    [...languagetoolKeys.all, "remote-tags", repo] as const,
};

export const useLanguageToolStatus = () =>
  useQuery<LanguageToolStatus>({
    queryKey: languagetoolKeys.status(),
    queryFn: () => languagetoolApi.status(),
    staleTime: 5_000,
    // While the container is up but not yet answering HTTP (LanguageTool boots
    // a JVM — can take 10-30s), poll so the UI flips to "running" on its own.
    refetchInterval: (query) => {
      const data = query.state.data;
      return data && data.container_running && !data.healthy ? 2_000 : false;
    },
  });

export const useLanguageToolImages = () =>
  useQuery<LanguageToolImagesList>({
    queryKey: languagetoolKeys.images(),
    queryFn: () => languagetoolApi.images(),
    staleTime: 5_000,
  });

export const useLanguageToolRemoteTags = (repo: string | null) =>
  useQuery<LanguageToolRemoteTags>({
    queryKey: languagetoolKeys.remoteTags(repo ?? ""),
    queryFn: () => languagetoolApi.listRemoteTags(repo!),
    enabled: repo !== null,
    // Docker Hub tag lists don't churn — cache 5 min so reopening the block
    // doesn't refetch, while a manual refresh still works.
    staleTime: 5 * 60_000,
  });

export const useInvalidateLanguageTool = () => {
  const queryClient = useQueryClient();
  return () => {
    void queryClient.invalidateQueries({ queryKey: languagetoolKeys.status() });
    void queryClient.invalidateQueries({ queryKey: languagetoolKeys.images() });
  };
};

export const useSetActiveLanguageToolImage = () => {
  const queryClient = useQueryClient();
  return useMutation<SetActiveLanguageToolImage, Error, string>({
    mutationFn: (image) => languagetoolApi.setActive(image),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: languagetoolKeys.all });
    },
  });
};

export const useRemoveLanguageToolImage = () => {
  const queryClient = useQueryClient();
  return useMutation<string, Error, string>({
    mutationFn: (image) => languagetoolApi.remove(image),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: languagetoolKeys.all });
    },
  });
};
