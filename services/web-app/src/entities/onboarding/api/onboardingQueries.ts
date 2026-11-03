import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { onboardingApi } from "./onboardingApi";
import type { OnboardingState, OnboardingUpdate } from "./onboardingSchemas";

export const onboardingKeys = {
  all: ["onboarding"] as const,
  state: () => [...onboardingKeys.all, "state"] as const,
};

export const useOnboardingState = (options?: { enabled?: boolean }) =>
  useQuery({
    queryKey: onboardingKeys.state(),
    queryFn: () => onboardingApi.get(),
    staleTime: Infinity,
    retry: false,
    enabled: options?.enabled ?? true,
  });

const useApply = () => {
  const queryClient = useQueryClient();
  return (state: OnboardingState) => {
    queryClient.setQueryData(onboardingKeys.state(), state);
  };
};

export const useUpdateOnboarding = () => {
  const apply = useApply();
  return useMutation({
    mutationFn: (body: OnboardingUpdate) => onboardingApi.update(body),
    onSuccess: apply,
  });
};

export const useResetOnboarding = () => {
  const apply = useApply();
  return useMutation({
    mutationFn: () => onboardingApi.reset(),
    onSuccess: apply,
  });
};
