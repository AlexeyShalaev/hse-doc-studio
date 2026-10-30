import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
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

export const useProjectAccess = (projectId: string) =>
  useQuery({
    queryKey: projectAccessKeys.list(projectId),
    queryFn: () => projectAccessApi.list(projectId),
    staleTime: 10_000,
  });

export const useAccessCandidates = (
  projectId: string,
  q: string,
  enabled: boolean,
) =>
  useQuery({
    queryKey: projectAccessKeys.candidates(projectId, q),
    queryFn: () => projectAccessApi.candidates(projectId, q),
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
