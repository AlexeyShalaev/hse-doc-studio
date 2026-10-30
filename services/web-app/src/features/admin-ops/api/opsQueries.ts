import { useCallback, useMemo } from "react";
import {
  keepPreviousData,
  useMutation,
  useQueries,
  useQuery,
  useQueryClient,
} from "@tanstack/react-query";
import type {
  AdminUser,
  CreateAdminRunnerTokenRequest,
  UpdateAdminQuotasRequest,
} from "@entities/session";
import type { OpsPerson } from "../lib/people";
import { opsApi, type QueueQuery } from "./opsApi";

export const opsKeys = {
  runners: ["admin", "ops", "runners"] as const,
  tokens: ["admin", "ops", "runner-tokens"] as const,
  queue: (query: QueueQuery) => ["admin", "ops", "queue", query] as const,
  queueAll: ["admin", "ops", "queue"] as const,
  summary: ["admin", "ops", "queue-summary"] as const,
  quotas: ["admin", "ops", "quotas"] as const,
  services: ["admin", "ops", "services"] as const,
  storage: ["admin", "ops", "storage"] as const,
  person: (id: string) => ["admin", "ops", "person", id] as const,
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

/** Имена и почты людей по идентификаторам; кого не нашли, в ответе нет. Люди меняются редко. */
export const usePeople = (
  ids: readonly string[],
): ReadonlyMap<string, OpsPerson> => {
  const unique = useMemo(
    () => [...new Set(ids.filter((id) => id !== ""))].sort(),
    [ids],
  );
  const combine = useCallback(
    (results: { data?: AdminUser | undefined }[]) => {
      const map = new Map<string, OpsPerson>();
      results.forEach((r, i) => {
        const id = unique[i];
        if (id !== undefined && r.data) {
          map.set(id, { name: r.data.name, email: r.data.email });
        }
      });
      return map;
    },
    [unique],
  );
  return useQueries({
    queries: unique.map((id) => ({
      queryKey: opsKeys.person(id),
      queryFn: () => opsApi.person(id),
      staleTime: 5 * 60_000,
      retry: false,
    })),
    combine,
  });
};

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
