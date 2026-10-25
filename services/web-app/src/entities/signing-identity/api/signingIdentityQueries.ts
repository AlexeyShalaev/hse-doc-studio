import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import type {
  CreateSelfSignedRequest,
  GenerateOpenPgpKeyRequest,
  UpdateSlotConfigRequest,
} from "./signingIdentitySchemas";
import { signingIdentityApi } from "./signingIdentityApi";

export const signingIdentityKeys = {
  all: ["signing-identities"] as const,
  list: () => [...signingIdentityKeys.all, "list"] as const,
};

export const useSigningIdentities = () =>
  useQuery({
    queryKey: signingIdentityKeys.list(),
    queryFn: () => signingIdentityApi.list(),
  });

export const useCreateSelfSigned = () => {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (data: CreateSelfSignedRequest) =>
      signingIdentityApi.createSelfSigned(data),
    onSuccess: () => {
      void queryClient.invalidateQueries({
        queryKey: signingIdentityKeys.list(),
      });
    },
  });
};

export const useImportPkcs12 = () => {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({
      label,
      file,
      passphrase,
    }: {
      label: string;
      file: File;
      passphrase?: string;
    }) => signingIdentityApi.importPkcs12(label, file, passphrase),
    onSuccess: () => {
      void queryClient.invalidateQueries({
        queryKey: signingIdentityKeys.list(),
      });
    },
  });
};

export const useDeleteSigningIdentity = () => {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (id: string) => signingIdentityApi.delete(id),
    onSuccess: () => {
      void queryClient.invalidateQueries({
        queryKey: signingIdentityKeys.all,
      });
    },
  });
};

export const useOpenPgpKeys = () =>
  useQuery({
    queryKey: [...signingIdentityKeys.all, "openpgp-keys"] as const,
    queryFn: () => signingIdentityApi.listOpenPgpKeys(),
  });

export const useGenerateOpenPgpKey = () => {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (data: GenerateOpenPgpKeyRequest) =>
      signingIdentityApi.generateOpenPgp(data),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: signingIdentityKeys.all });
    },
  });
};

export const useImportOpenPgpKey = () => {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({
      file,
      passphrase,
      label,
    }: {
      file: File;
      passphrase?: string;
      label?: string;
    }) => signingIdentityApi.importOpenPgp(file, passphrase, label),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: signingIdentityKeys.all });
    },
  });
};

export const trustedRootKeys = {
  list: () => ["trusted-roots", "list"] as const,
};

export const useTrustedRoots = () =>
  useQuery({
    queryKey: trustedRootKeys.list(),
    queryFn: () => signingIdentityApi.listTrustedRoots(),
  });

export const useAddTrustedRoot = () => {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (file: File) => signingIdentityApi.addTrustedRoot(file),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: trustedRootKeys.list() });
    },
  });
};

export const useDeleteTrustedRoot = () => {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (fingerprint: string) =>
      signingIdentityApi.deleteTrustedRoot(fingerprint),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: trustedRootKeys.list() });
    },
  });
};

export const useUpdateSlotConfig = () => {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({
      projectId,
      slotId,
      data,
    }: {
      projectId: string;
      slotId: string;
      data: UpdateSlotConfigRequest;
    }) => signingIdentityApi.updateSlotConfig(projectId, slotId, data),
    onSuccess: (_, { projectId }) => {
      // Invalidate signatures state so SlotPanel reflects new signing_identity_id.
      void queryClient.invalidateQueries({
        queryKey: ["signatures", "state", projectId],
      });
    },
  });
};
