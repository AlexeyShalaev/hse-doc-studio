import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import type { UpdatePlacementRequest } from "@shared/api/types";
import { signatureApi } from "./signatureApi";

type SignaturesState = Awaited<ReturnType<typeof signatureApi.getState>>;
type Placement = Awaited<ReturnType<typeof signatureApi.updatePlacement>>;
type UploadResult = Awaited<ReturnType<typeof signatureApi.uploadPng>>;

export const signatureKeys = {
  all: ["signatures"] as const,
  state: (projectId: string) =>
    [...signatureKeys.all, "state", projectId] as const,
};

export const useSignaturesState = (projectId: string) =>
  useQuery<SignaturesState>({
    queryKey: signatureKeys.state(projectId),
    queryFn: () => signatureApi.getState(projectId),
    enabled: !!projectId,
  });

export const useUpdateSignaturePlacement = () => {
  const queryClient = useQueryClient();
  return useMutation<
    Placement,
    Error,
    {
      projectId: string;
      docId: string;
      slotId: string;
      data: UpdatePlacementRequest;
    }
  >({
    mutationFn: ({ projectId, docId, slotId, data }) =>
      signatureApi.updatePlacement(projectId, docId, slotId, data),
    onSuccess: (_, { projectId }) => {
      void queryClient.invalidateQueries({
        queryKey: signatureKeys.state(projectId),
      });
    },
  });
};

export const useUploadSignaturePng = () => {
  const queryClient = useQueryClient();
  return useMutation<
    UploadResult,
    Error,
    { projectId: string; slotId: string; file: File }
  >({
    mutationFn: ({ projectId, slotId, file }) =>
      signatureApi.uploadPng(projectId, slotId, file),
    onSuccess: (_, { projectId }) => {
      void queryClient.invalidateQueries({
        queryKey: signatureKeys.state(projectId),
      });
    },
  });
};

export const useDeleteSignaturePng = () => {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({
      projectId,
      slotId,
    }: {
      projectId: string;
      slotId: string;
    }) => signatureApi.deletePng(projectId, slotId),
    onSuccess: (_, { projectId }) => {
      void queryClient.invalidateQueries({
        queryKey: signatureKeys.state(projectId),
      });
    },
  });
};
