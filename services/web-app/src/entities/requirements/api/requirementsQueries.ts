import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  requirementsApi,
  type RequirementFormat,
  type RequirementsMatrix,
} from "./requirementsApi";

export const requirementsKeys = {
  all: ["requirements"] as const,
  matrix: (projectId: string) =>
    [...requirementsKeys.all, "matrix", projectId] as const,
};

export const useRequirements = (projectId: string) =>
  useQuery<RequirementsMatrix>({
    queryKey: requirementsKeys.matrix(projectId),
    queryFn: () => requirementsApi.get(projectId),
    enabled: !!projectId,
  });

export const useUpdateRequirementsFormat = (projectId: string) => {
  const queryClient = useQueryClient();
  return useMutation<RequirementsMatrix, Error, RequirementFormat | null>({
    mutationFn: (format) => requirementsApi.updateFormat(projectId, format),
    onSuccess: (data) => {
      // The PUT returns the freshly rebuilt matrix — prime the cache with it.
      queryClient.setQueryData(requirementsKeys.matrix(projectId), data);
    },
  });
};
