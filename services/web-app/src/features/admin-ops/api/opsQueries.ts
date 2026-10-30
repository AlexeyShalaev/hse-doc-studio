import {
  keepPreviousData,
  useMutation,
  useQuery,
  useQueryClient,
} from "@tanstack/react-query";
import type {
  CreateAdminRunnerTokenRequest,
  UpdateAdminQuotasRequest,
} from "@entities/session";
import { opsApi, type QueueQuery } from "./opsApi";

export const opsKeys = {
  runners: ["admin", "ops", "runners"] as const,
  tokens: ["admin", "ops", "runner-tokens"] as const,
  queue: (query: QueueQuery) => ["admin", "ops", "queue", query] as const,
  queueAll: ["admin", "ops", "queue"] as const,
  summary: ["admin", "ops", "queue-summary"] as const,
  quotas: ["admin", "ops", "quotas"] as const,
  orgs: ["admin", "ops", "orgs"] as const,
  services: ["admin", "ops", "services"] as const,
  storage: ["admin", "ops", "storage"] as const,
};

/** Опрос идёт только пока вкладка видна: react-query не тикает в фоне без явного флага. */
const POLL_MS = 5000;

export const useRunners = () =>
  useQuery({
    queryKey: opsKeys.runners,
    queryFn: () => opsApi.runners(),
    staleTime: 0,
    refetchInterval: POLL_MS * 3,
  });

export const useTokens = () =>
  useQuery({
    queryKey: opsKeys.tokens,
    queryFn: () => opsApi.tokens(),
    staleTime: 0,
  });

export const useQueue = (query: QueueQuery) =>
  useQuery({
    queryKey: opsKeys.queue(query),
    queryFn: () => opsApi.queue(query),
    staleTime: 0,
    refetchInterval: POLL_MS,
    placeholderData: keepPreviousData,
  });

export const useQueueSummary = () =>
  useQuery({
    queryKey: opsKeys.summary,
    queryFn: () => opsApi.queueSummary(),
    staleTime: 0,
    refetchInterval: POLL_MS,
  });

export const useQuotas = () =>
  useQuery({
    queryKey: opsKeys.quotas,
    queryFn: () => opsApi.quotas(),
    staleTime: 0,
  });

export const useOrgChoices = () =>
  useQuery({
    queryKey: opsKeys.orgs,
    queryFn: () => opsApi.orgs(),
    staleTime: 30000,
  });

export const useServices = () =>
  useQuery({
    queryKey: opsKeys.services,
    queryFn: () => opsApi.services(),
    staleTime: 0,
    refetchInterval: POLL_MS * 6,
  });

export const useStorage = () =>
  useQuery({
    queryKey: opsKeys.storage,
    queryFn: () => opsApi.storage(),
    staleTime: 0,
  });

const useInvalidate = () => {
  const client = useQueryClient();
  return (...keys: readonly (readonly unknown[])[]) => {
    for (const queryKey of keys) void client.invalidateQueries({ queryKey });
  };
};

export const useSetPaused = () => {
  const invalidate = useInvalidate();
  return useMutation({
    mutationFn: (v: { id: string; paused: boolean }) =>
      opsApi.setPaused(v.id, v.paused),
    onSuccess: () => {
      invalidate(opsKeys.runners);
    },
  });
};

export const useRotateToken = () => {
  const invalidate = useInvalidate();
  return useMutation({
    mutationFn: (id: string) => opsApi.rotateToken(id),
    onSuccess: () => {
      invalidate(opsKeys.runners);
    },
  });
};

export const useRevokeRunner = () => {
  const invalidate = useInvalidate();
  return useMutation({
    mutationFn: (id: string) => opsApi.revokeRunner(id),
    onSuccess: () => {
      invalidate(opsKeys.runners);
    },
  });
};

/** Секрет не кладём в кэш запросов: он живёт только в состоянии компонента. */
export const useCreateToken = () => {
  const invalidate = useInvalidate();
  return useMutation({
    mutationFn: (body: CreateAdminRunnerTokenRequest) =>
      opsApi.createToken(body),
    gcTime: 0,
    onSuccess: () => {
      invalidate(opsKeys.tokens);
    },
  });
};

export const useRevokeToken = () => {
  const invalidate = useInvalidate();
  return useMutation({
    mutationFn: (id: string) => opsApi.revokeToken(id),
    onSuccess: () => {
      invalidate(opsKeys.tokens);
    },
  });
};

export const useCancelJob = () => {
  const invalidate = useInvalidate();
  return useMutation({
    mutationFn: (id: string) => opsApi.cancelJob(id),
    onSettled: () => {
      invalidate(opsKeys.queueAll, opsKeys.summary);
    },
  });
};

export const useUpdateQuotas = () => {
  const invalidate = useInvalidate();
  return useMutation({
    mutationFn: (body: UpdateAdminQuotasRequest) => opsApi.updateQuotas(body),
    onSuccess: () => {
      invalidate(opsKeys.quotas);
    },
  });
};

export const useSetOverride = () => {
  const invalidate = useInvalidate();
  return useMutation({
    mutationFn: (v: { slug: string; body: UpdateAdminQuotasRequest }) =>
      opsApi.setOverride(v.slug, v.body),
    onSuccess: () => {
      invalidate(opsKeys.quotas);
    },
  });
};

export const useClearOverride = () => {
  const invalidate = useInvalidate();
  return useMutation({
    mutationFn: (slug: string) => opsApi.clearOverride(slug),
    onSuccess: () => {
      invalidate(opsKeys.quotas);
    },
  });
};

export const useCheckService = () => {
  const invalidate = useInvalidate();
  return useMutation({
    mutationFn: (id: string) => opsApi.checkService(id),
    onSuccess: () => {
      invalidate(opsKeys.services);
    },
  });
};
