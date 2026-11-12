import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import type { UpdatePlacementRequest } from "@shared/api/types";
import { signatureApi, type SignSubmissionBody } from "./signatureApi";

type SignaturesState = Awaited<ReturnType<typeof signatureApi.getState>>;
type Placement = Awaited<ReturnType<typeof signatureApi.updatePlacement>>;
type UploadResult = Awaited<ReturnType<typeof signatureApi.uploadPng>>;
type FreezeResult = Awaited<ReturnType<typeof signatureApi.freezePdf>>;
type AttachResult = Awaited<ReturnType<typeof signatureApi.attachDetached>>;

export const signatureKeys = {
  all: ["signatures"] as const,
  state: (projectId: string) =>
    [...signatureKeys.all, "state", projectId] as const,
  // Под ключом состояния: любая мутация подписей уже сбрасывает state, и план
  // пересчитывается вместе с ним без отдельной инвалидации в каждой мутации.
  plan: (
    projectId: string,
    profileId: string | null | undefined,
    author: string | null | undefined,
  ) =>
    [
      ...signatureKeys.state(projectId),
      "plan",
      profileId ?? "",
      author ?? "",
    ] as const,
};

type SignaturePlan = Awaited<ReturnType<typeof signatureApi.getPlan>>;

/**
 * План подписей одного документа. Вместе с ним приходит маршрут подписания, который держит
 * документ (`route`), поэтому редактору документа хватает одного запроса.
 */
export const useDocSignaturePlan = (
  projectId: string,
  docId: string,
  options: { enabled?: boolean } = {},
) =>
  useQuery<SignaturePlan>({
    queryKey: [...signatureKeys.state(projectId), "doc-plan", docId] as const,
    queryFn: ({ signal }) => signatureApi.getPlan(projectId, { docId }, signal),
    enabled: (options.enabled ?? true) && !!projectId && !!docId,
    staleTime: 60_000,
    retry: false,
  });

export const useSignaturePlan = (
  projectId: string,
  profileId: string | null | undefined,
  author: string | null | undefined,
) =>
  useQuery<SignaturePlan>({
    queryKey: signatureKeys.plan(projectId, profileId, author),
    queryFn: () => signatureApi.getPlan(projectId, { profileId, author }),
    enabled: !!projectId,
  });

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

/** «Показать» придержанную маршрутом картинку: план и предпросмотр сбрасываются вместе с состоянием. */
export const useReleaseWithheld = () => {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({
      projectId,
      docId,
      slotId,
    }: {
      projectId: string;
      docId: string;
      slotId: string;
    }) => signatureApi.releaseWithheld(projectId, docId, slotId),
    onSuccess: (_, { projectId }) => {
      void queryClient.invalidateQueries({
        queryKey: signatureKeys.state(projectId),
      });
    },
  });
};

/**
 * «Подпись необязательна» (signing-route.md, 13.6). Флаг меняет план, пропуск в маршруте и его
 * задачи, поэтому сбрасываются и состояние подписей, и запросы маршрутов проекта (ключ
 * `signingRouteKeys.project` сущности маршрута: сущности друг друга не импортируют).
 */
export const useSetSlotOptional = () => {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({
      projectId,
      docId,
      slotId,
      profileId,
      optional,
    }: {
      projectId: string;
      docId: string;
      slotId: string;
      profileId: string;
      optional: boolean;
    }) =>
      signatureApi.setSlotOptional(projectId, docId, slotId, {
        profile_id: profileId,
        optional,
      }),
    onSettled: (_data, _error, { projectId }) => {
      void queryClient.invalidateQueries({
        queryKey: signatureKeys.state(projectId),
      });
      void queryClient.invalidateQueries({
        queryKey: ["signing-routes", "project", projectId],
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

/** «Подписывать текущую сборку»: план и состояние подписей перечитываются под ключом state. */
export const useUnpinSignedVersion = () => {
  const invalidate = useInvalidateSignatures();
  return useMutation({
    mutationFn: ({ projectId, docId }: { projectId: string; docId: string }) =>
      signatureApi.unpinVersion(projectId, docId),
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

export const useSetSlotSigner = () => {
  const invalidate = useInvalidateSignatures();
  return useMutation({
    mutationFn: ({
      projectId,
      slotId,
      ...source
    }: { projectId: string; slotId: string } & (
      | { file: File }
      | { identityId: string }
      | { owner: string; certId?: string; validTo?: string | null }
    )) => {
      if ("file" in source) {
        return signatureApi.setSignerFromFile(projectId, slotId, source.file);
      }
      if ("identityId" in source) {
        return signatureApi.setSigner(projectId, slotId, {
          identity_id: source.identityId,
        });
      }
      return signatureApi.setSigner(projectId, slotId, {
        owner: source.owner,
        cert_id: source.certId ?? "",
        valid_to: source.validTo ?? null,
      });
    },
    onSuccess: (_, { projectId }) => void invalidate(projectId),
  });
};

export const useClearSlotSigner = () => {
  const invalidate = useInvalidateSignatures();
  return useMutation({
    mutationFn: ({
      projectId,
      slotId,
    }: {
      projectId: string;
      slotId: string;
    }) => signatureApi.clearSigner(projectId, slotId),
    onSuccess: (_, { projectId }) => void invalidate(projectId),
  });
};

export const useSetSignerLevel = () => {
  const invalidate = useInvalidateSignatures();
  return useMutation({
    mutationFn: ({
      projectId,
      slotId,
      level,
    }: {
      projectId: string;
      slotId: string;
      level: string;
    }) => signatureApi.setSignerLevel(projectId, slotId, level),
    onSuccess: (_, { projectId }) => void invalidate(projectId),
  });
};

export const useCompleteChain = () => {
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
    }) => signatureApi.completeChain(projectId, docId, slotId),
    onSuccess: (_, { projectId }) => void invalidate(projectId),
  });
};

export const useTrustRoot = () => {
  const invalidate = useInvalidateSignatures();
  return useMutation({
    mutationFn: ({
      fingerprint,
    }: {
      projectId: string;
      docId: string;
      slotId: string;
      fingerprint: string;
    }) => signatureApi.trustRootFromChain(fingerprint),
    // The signature is checked again so the chain flips to "trusted".
    onSuccess: async (_, { projectId, docId, slotId }) => {
      await signatureApi.recheckDetached(projectId, docId, slotId);
      await invalidate(projectId);
    },
  });
};

export const usePreviewSignSubmission = () =>
  useMutation({
    mutationFn: ({
      projectId,
      body,
    }: {
      projectId: string;
      body: SignSubmissionBody;
    }) => signatureApi.previewSignSubmission(projectId, body),
  });

export const useSignSubmission = () => {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({
      projectId,
      body,
    }: {
      projectId: string;
      body: SignSubmissionBody;
    }) => signatureApi.signSubmission(projectId, body),
    onSettled: (_data, _error, { projectId }) => {
      void queryClient.invalidateQueries({
        queryKey: signatureKeys.state(projectId),
      });
    },
  });
};
