import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { aiProviderApiFor, type AIProviderOwner } from "./aiProviderApi";
import type {
  AIProvider,
  CreateAIProviderInput,
  UpdateAIProviderInput,
} from "../model/aiProvider.schema";

export const aiProviderKeys = {
  all: ["ai-providers"] as const,
  lists: () => [...aiProviderKeys.all, "list"] as const,
  instanceLists: () => [...aiProviderKeys.all, "instance", "list"] as const,
};

const listKey = (owner: AIProviderOwner) =>
  owner === "instance"
    ? aiProviderKeys.instanceLists()
    : aiProviderKeys.lists();

export const useAIProviders = (owner: AIProviderOwner = "user") =>
  useQuery<AIProvider[]>({
    queryKey: listKey(owner),
    queryFn: () => aiProviderApiFor(owner).list(),
    staleTime: 60_000,
  });

export const useCreateAIProvider = (owner: AIProviderOwner = "user") => {
  const queryClient = useQueryClient();
  return useMutation<AIProvider, Error, CreateAIProviderInput>({
    mutationFn: (body) => aiProviderApiFor(owner).create(body),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: aiProviderKeys.all });
    },
  });
};

export const useUpdateAIProvider = (owner: AIProviderOwner = "user") => {
  const queryClient = useQueryClient();
  return useMutation<
    AIProvider,
    Error,
    { id: string; body: UpdateAIProviderInput }
  >({
    mutationFn: ({ id, body }) => aiProviderApiFor(owner).update(id, body),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: aiProviderKeys.all });
    },
  });
};

export const useDeleteAIProvider = (owner: AIProviderOwner = "user") => {
  const queryClient = useQueryClient();
  return useMutation<string, Error, string>({
    mutationFn: (id) => aiProviderApiFor(owner).remove(id),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: aiProviderKeys.all });
    },
  });
};
