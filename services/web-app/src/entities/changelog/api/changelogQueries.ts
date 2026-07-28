import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import type {
  AddChangeLogEntryRequest,
  ChangeLogEntryResponse,
} from "@shared/api/types";
import { changelogApi } from "./changelogApi";

export const changelogKeys = {
  all: ["changelog"] as const,
  list: (projectId: string, docId?: string) =>
    [...changelogKeys.all, "list", projectId, docId ?? "all"] as const,
};

export const useChangelog = (projectId: string, docId?: string) =>
  useQuery<ChangeLogEntryResponse[]>({
    queryKey: changelogKeys.list(projectId, docId),
    queryFn: () => changelogApi.list(projectId, docId),
    enabled: !!projectId,
  });

export const useAddChangelogNote = () => {
  const queryClient = useQueryClient();
  return useMutation<
    ChangeLogEntryResponse,
    Error,
    { projectId: string; data: AddChangeLogEntryRequest }
  >({
    mutationFn: ({ projectId, data }) => changelogApi.addNote(projectId, data),
    onSuccess: (_, { projectId }) => {
      void queryClient.invalidateQueries({
        queryKey: changelogKeys.list(projectId),
      });
    },
  });
};
