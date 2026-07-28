import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { aiProviderApi } from "./aiProviderApi";
import type {
  AIProvider,
  CreateAIProviderInput,
  UpdateAIProviderInput,
} from "../model/aiProvider.schema";

export const aiProviderKeys = {
  all: ["ai-providers"] as const,
  lists: () => [...aiProviderKeys.all, "list"] as const,
};

export const useAIProviders = () =>
  useQuery<AIProvider[]>({
    queryKey: aiProviderKeys.lists(),
    queryFn: () => aiProviderApi.list(),
    staleTime: 60_000,
  });

export const useCreateAIProvider = () => {
  const queryClient = useQueryClient();
  return useMutation<AIProvider, Error, CreateAIProviderInput>({
    mutationFn: (body) => aiProviderApi.create(body),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: aiProviderKeys.lists() });
    },
  });
};

export const useUpdateAIProvider = () => {
  const queryClient = useQueryClient();
  return useMutation<
    AIProvider,
    Error,
    { id: string; body: UpdateAIProviderInput }
  >({
    mutationFn: ({ id, body }) => aiProviderApi.update(id, body),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: aiProviderKeys.lists() });
    },
  });
};

export const useDeleteAIProvider = () => {
  const queryClient = useQueryClient();
  return useMutation<string, Error, string>({
    mutationFn: (id) => aiProviderApi.remove(id),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: aiProviderKeys.lists() });
    },
  });
};
