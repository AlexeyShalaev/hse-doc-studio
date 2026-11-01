import {
  keepPreviousData,
  useMutation,
  useQuery,
  useQueryClient,
} from "@tanstack/react-query";
import { PICKER_LIMIT, type ListRequestParams } from "@shared/lib";
import {
  projectAccessApi,
  type SetProjectAccessRequest,
} from "./projectAccessApi";

export const projectAccessKeys = {
  all: ["project-access"] as const,
  list: (projectId: string) =>
    [...projectAccessKeys.all, projectId, "list"] as const,
  candidates: (projectId: string, q: string) =>
    [...projectAccessKeys.all, projectId, "candidates", q] as const,
};

/** Страница списка доступа: поиск, вид и окно считает сервер. */
export const useProjectAccess = (
  projectId: string,
  params: ListRequestParams,
) =>
  useQuery({
    queryKey: [...projectAccessKeys.list(projectId), params],
    queryFn: ({ signal }) => projectAccessApi.list(projectId, params, signal),
    placeholderData: keepPreviousData,
    staleTime: 10_000,
  });

export const useAccessCandidates = (
  projectId: string,
  q: string,
  enabled: boolean,
) =>
  useQuery({
    queryKey: projectAccessKeys.candidates(projectId, q),
    queryFn: ({ signal }) =>
      projectAccessApi.candidates(projectId, q, PICKER_LIMIT, signal),
    placeholderData: keepPreviousData,
    enabled,
    staleTime: 5_000,
  });

export const useSetAccess = (projectId: string) => {
  const client = useQueryClient();
  return useMutation({
    mutationFn: (body: SetProjectAccessRequest) =>
      projectAccessApi.set(projectId, body),
    onSettled: () =>
      client.invalidateQueries({ queryKey: projectAccessKeys.all }),
  });
};

export const useRemoveAccess = (projectId: string) => {
  const client = useQueryClient();
  return useMutation({
    mutationFn: (p: { kind: "user" | "group"; id: string }) =>
      projectAccessApi.remove(projectId, p.kind, p.id),
    onSettled: () =>
      client.invalidateQueries({ queryKey: projectAccessKeys.all }),
  });
};
