import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import type {
  AdminUser,
  CreateAdminRunnerTokenRequest,
  UpdateAdminQuotasRequest,
} from "@entities/session";
import { opsApi } from "./opsApi";

// Списки (раннеры, токены, очередь, владельцы места) живут в хуках серверных
// списков (useServerList, useCursorList): ключ там [...начало, "list" | "log", params].
// Здесь начала ключей, по которым мутации сбрасывают все страницы разом.
export const opsKeys = {
  runners: ["admin", "ops", "runners"] as const,
  runnerSummary: ["admin", "ops", "runner-summary"] as const,
  tokens: ["admin", "ops", "runner-tokens"] as const,
  queueAll: ["admin", "ops", "queue"] as const,
  /** Выполняющиеся задачи для занятости раннеров: отдельно от списка очереди. */
  running: ["admin", "ops", "running"] as const,
  summary: ["admin", "ops", "queue-summary"] as const,
  quotas: ["admin", "ops", "quotas"] as const,
  services: ["admin", "ops", "services"] as const,
  storage: ["admin", "ops", "storage"] as const,
  storageOwners: ["admin", "ops", "storage-owners"] as const,
  person: (id: string) => ["admin", "ops", "person", id] as const,
  buildSettings: ["admin", "ops", "build-settings"] as const,
  personalRunners: ["admin", "ops", "runners", "personal"] as const,
};

/** Опрос идёт только пока вкладка видна: react-query не тикает в фоне без явного флага. */
export const POLL_MS = 5000;

/** Счётчики раннеров: плитки «Раннеров» и «Обзора», вкладка и навигация. */
export const useRunnerSummary = () =>
  useQuery({
    queryKey: opsKeys.runnerSummary,
    queryFn: () => opsApi.runnerSummary(),
    staleTime: 0,
    refetchInterval: POLL_MS * 3,
  });

// Личных раннеров на установке немного: читаются одним окном без страниц
// в адресе, владелец раннера приходит в каждой строке от сервера.
const PERSONAL_RUNNERS_WINDOW = 200;

export const usePersonalRunners = () =>
  useQuery({
    queryKey: opsKeys.personalRunners,
    queryFn: ({ signal }) =>
      opsApi
        .runners(
          { owner_kind: "user", limit: PERSONAL_RUNNERS_WINDOW },
          signal,
        )
        .then((page) => page.items),
    staleTime: 0,
    refetchInterval: POLL_MS * 3,
  });

/** Разрешены ли личные раннеры на установке: из настроек сборки. */
export const usePersonalRunnersEnabled = () =>
  useQuery({
    queryKey: opsKeys.buildSettings,
    queryFn: () => opsApi.buildSettings(),
    staleTime: 30_000,
    select: (settings) => settings.personal_runners_enabled,
  });

// Сколько выполняющихся задач читается ради занятости раннеров. Их не больше,
// чем мест у раннеров; если всё же больше, занятость не показывается, а не врёт.
const RUNNING_WINDOW = 200;

/** Выполняющиеся задачи одной страницей; null, если их больше окна. */
export const useRunningJobs = () =>
  useQuery({
    queryKey: opsKeys.running,
    queryFn: async ({ signal }) => {
      const page = await opsApi.queue(
        { state: ["running"], limit: RUNNING_WINDOW },
        signal,
      );
      return page.next_cursor === null ? page.items : null;
    },
    staleTime: 0,
    refetchInterval: POLL_MS * 3,
  });

/** Сколько из выполняющихся задач сейчас на личных раннерах; null, если их больше окна. */
export const usePersonalRunningJobs = () =>
  useQuery({
    queryKey: ["admin", "ops", "running", "personal"] as const,
    queryFn: async ({ signal }) => {
      const page = await opsApi.queue(
        { state: ["running"], runner_scope: "personal", limit: RUNNING_WINDOW },
        signal,
      );
      return page.next_cursor === null ? page.items : null;
    },
    staleTime: 0,
    refetchInterval: POLL_MS * 3,
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
      invalidate(opsKeys.runners, opsKeys.runnerSummary);
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
      invalidate(opsKeys.runners, opsKeys.runnerSummary);
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
      invalidate(opsKeys.queueAll, opsKeys.summary, opsKeys.running);
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
