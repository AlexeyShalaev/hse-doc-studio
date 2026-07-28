import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  imagesApi,
  type DockerStatus,
  type ImagesListResponse,
  type RemoteTagsResponse,
  type SetActiveImageResponse,
} from "./imagesApi";

export const imagesKeys = {
  all: ["compile-images"] as const,
  dockerStatus: () => [...imagesKeys.all, "docker-status"] as const,
  list: () => [...imagesKeys.all, "list"] as const,
  remoteTags: (repo: string) =>
    [...imagesKeys.all, "remote-tags", repo] as const,
};

export const useDockerStatus = () =>
  useQuery<DockerStatus>({
    queryKey: imagesKeys.dockerStatus(),
    queryFn: () => imagesApi.dockerStatus(),
    // Poll-ish behaviour: refetch on focus and stale, so when user fixes
    // Docker (starts daemon) the banner resolves quickly without a manual
    // reload.
    staleTime: 10_000,
  });

export const useImagesList = () =>
  useQuery<ImagesListResponse>({
    queryKey: imagesKeys.list(),
    queryFn: () => imagesApi.list(),
    staleTime: 5_000,
  });

export const useRemoteTags = (repo: string | null) =>
  useQuery<RemoteTagsResponse>({
    queryKey: imagesKeys.remoteTags(repo ?? ""),
    queryFn: () => imagesApi.listRemoteTags(repo!),
    enabled: repo !== null,
    // Docker Hub tag lists don't churn — 5min cache means switching tabs
    // and coming back doesn't refetch unnecessarily, but a manual refresh
    // (refetch) still works for "I just published a new tag" cases.
    staleTime: 5 * 60_000,
  });

export const useInvalidateImages = () => {
  const queryClient = useQueryClient();
  return () => {
    void queryClient.invalidateQueries({ queryKey: imagesKeys.list() });
    void queryClient.invalidateQueries({ queryKey: imagesKeys.dockerStatus() });
  };
};

export const useSetActiveImage = () => {
  const queryClient = useQueryClient();
  return useMutation<SetActiveImageResponse, Error, string>({
    mutationFn: (image) => imagesApi.setActive(image),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: imagesKeys.list() });
      // The user-settings cache also stores `compile_image`; refresh it so
      // any view that branches on the active tag stays in sync.
      void queryClient.invalidateQueries({ queryKey: ["settings"] });
    },
  });
};

export const useRemoveImage = () => {
  const queryClient = useQueryClient();
  return useMutation<string, Error, string>({
    mutationFn: (image) => imagesApi.remove(image),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: imagesKeys.list() });
    },
  });
};
