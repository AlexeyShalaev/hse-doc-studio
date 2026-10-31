import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { projectArtifactApi } from "./artifactApi";

export const projectArtifactKeys = {
  all: ["project-artifacts"] as const,
  list: (projectId: string) => ["project-artifacts", projectId] as const,
};

/** PDF локальной сборки, выгруженные на сервер; `enabled` только там, где сервер умеет принимать их. */
export const useProjectArtifacts = (projectId: string, enabled = true) =>
  useQuery({
    queryKey: projectArtifactKeys.list(projectId),
    queryFn: () => projectArtifactApi.list(projectId),
    enabled: enabled && !!projectId,
    retry: false,
    staleTime: 30_000,
  });

export const useDeleteProjectArtifact = () => {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({
      projectId,
      artifactId,
    }: {
      projectId: string;
      artifactId: string;
    }) => projectArtifactApi.remove(projectId, artifactId),
    onSuccess: (_, { projectId }) => {
      void queryClient.invalidateQueries({
        queryKey: projectArtifactKeys.list(projectId),
      });
    },
  });
};
