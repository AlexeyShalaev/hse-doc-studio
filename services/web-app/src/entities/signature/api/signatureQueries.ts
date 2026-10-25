import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import type { UpdatePlacementRequest } from "@shared/api/types";
import { signatureApi } from "./signatureApi";

type SignaturesState = Awaited<ReturnType<typeof signatureApi.getState>>;
type Placement = Awaited<ReturnType<typeof signatureApi.updatePlacement>>;
type UploadResult = Awaited<ReturnType<typeof signatureApi.uploadPng>>;
type FreezeResult = Awaited<ReturnType<typeof signatureApi.freezePdf>>;
type AttachResult = Awaited<ReturnType<typeof signatureApi.attachDetached>>;

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

const useInvalidateSignatures = () => {
  const queryClient = useQueryClient();
  return (projectId: string) =>
    queryClient.invalidateQueries({ queryKey: signatureKeys.state(projectId) });
};

export const useFreezePdf = () => {
  const invalidate = useInvalidateSignatures();
  return useMutation<FreezeResult, Error, { projectId: string; docId: string }>(
    {
      mutationFn: ({ projectId, docId }) =>
        signatureApi.freezePdf(projectId, docId),
      onSuccess: (_, { projectId }) => void invalidate(projectId),
    },
  );
};

export const useUnfreezePdf = () => {
  const invalidate = useInvalidateSignatures();
  return useMutation({
    mutationFn: ({ projectId, docId }: { projectId: string; docId: string }) =>
      signatureApi.unfreezePdf(projectId, docId),
    onSuccess: (_, { projectId }) => void invalidate(projectId),
  });
};

export const useAttachDetachedSignature = () => {
  const invalidate = useInvalidateSignatures();
  return useMutation<
    AttachResult,
    Error,
    {
      projectId: string;
      docId: string;
      slotId: string;
      file: File;
      publicKey?: File;
    }
  >({
    mutationFn: ({ projectId, docId, slotId, file, publicKey }) =>
      signatureApi.attachDetached(projectId, docId, slotId, file, publicKey),
    onSuccess: (_, { projectId }) => void invalidate(projectId),
  });
};

export const useRecheckDetachedSignature = () => {
  const invalidate = useInvalidateSignatures();
  return useMutation<
    AttachResult,
    Error,
    { projectId: string; docId: string; slotId: string; publicKey?: File }
  >({
    mutationFn: ({ projectId, docId, slotId, publicKey }) =>
      signatureApi.recheckDetached(projectId, docId, slotId, publicKey),
    onSuccess: (_, { projectId }) => void invalidate(projectId),
  });
};

export const useSignDetachedInStudio = () => {
  const invalidate = useInvalidateSignatures();
  return useMutation<
    AttachResult,
    Error,
    {
      projectId: string;
      docId: string;
      slotId: string;
      identityId: string;
      passphrase: string;
    }
  >({
    mutationFn: ({ projectId, docId, slotId, identityId, passphrase }) =>
      signatureApi.signInStudio(
        projectId,
        docId,
        slotId,
        identityId,
        passphrase,
      ),
    onSuccess: (_, { projectId }) => void invalidate(projectId),
  });
};

export const useDeleteDetachedSignature = () => {
  const invalidate = useInvalidateSignatures();
  return useMutation({
    mutationFn: ({
      projectId,
      docId,
      slotId,
    }: {
      projectId: string;
      docId: string;
      slotId: string;
    }) => signatureApi.deleteDetached(projectId, docId, slotId),
    onSuccess: (_, { projectId }) => void invalidate(projectId),
  });
};
