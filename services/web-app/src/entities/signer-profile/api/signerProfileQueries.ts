import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { signerProfileApi } from "./signerProfileApi";
import type { SignerProfile } from "./signerProfileSchemas";

export const signerProfileKeys = {
  all: ["signer-profile"] as const,
};

export const useSignerProfile = (enabled = true) =>
  useQuery({
    queryKey: signerProfileKeys.all,
    queryFn: () => signerProfileApi.get(),
    enabled,
  });

const useProfileMutation = <T>(fn: (arg: T) => Promise<SignerProfile>) => {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: fn,
    onSuccess: (profile) => {
      queryClient.setQueryData(signerProfileKeys.all, profile);
    },
  });
};

export const useSaveProfileImage = () =>
  useProfileMutation((file: Blob) => signerProfileApi.saveImage(file));

export const useClearProfileImage = () =>
  useProfileMutation<undefined>(() => signerProfileApi.clearImage());

export const useSaveProfilePublicKey = () =>
  useProfileMutation((file: File) => signerProfileApi.savePublicKey(file));

export const useClearProfilePublicKey = () =>
  useProfileMutation<undefined>(() => signerProfileApi.clearPublicKey());
