import { useCallback } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import type {
  CreateAdminRunnerTokenRequest,
  SshProbeRequest,
  StartLocalInstallRequest,
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
  installLocal: ["admin", "ops", "runner-install", "local"] as const,
  installJob: (id: string) =>
    ["admin", "ops", "runner-install", "job", id] as const,
  installInstances: ["admin", "ops", "runner-install", "instances"] as const,
  sshCredentials: [
    "admin",
    "ops",
    "runner-install",
    "ssh-credentials",
  ] as const,
  sshCapability: ["admin", "ops", "runner-install", "ssh"] as const,
  runnerDeployment: (id: string) =>
    ["admin", "ops", "runners", "deployment", id] as const,
  runnerIsolation: ["admin", "ops", "runner-isolation"] as const,
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

/** Как развёрнут раннер: читается, пока открыта его карточка. */
export const useRunnerDeployment = (id: string | null) =>
  useQuery({
    queryKey: opsKeys.runnerDeployment(id ?? ""),
    queryFn: () => opsApi.runnerDeployment(id ?? ""),
    enabled: id !== null,
    staleTime: 15_000,
  });

/** Изоляция раннеров в кластере: меняется только с релизом, частый опрос не нужен. */
export const useRunnerIsolation = () =>
  useQuery({
    queryKey: opsKeys.runnerIsolation,
    queryFn: () => opsApi.runnerIsolation(),
    staleTime: 60_000,
  });

// Личных раннеров на установке немного: читаются одним окном без страниц
// в адресе, владелец раннера приходит в каждой строке от сервера.
const PERSONAL_RUNNERS_WINDOW = 200;

export const usePersonalRunners = () =>
  useQuery({
    queryKey: opsKeys.personalRunners,
    queryFn: ({ signal }) =>
      opsApi
        .runners({ owner_kind: "user", limit: PERSONAL_RUNNERS_WINDOW }, signal)
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

/** Возможности установки на этой машине: читаются при открытии окна, без фонового опроса. */
export const useLocalInstallCapabilities = (enabled: boolean) =>
  useQuery({
    queryKey: opsKeys.installLocal,
    queryFn: () => opsApi.localCapabilities(),
    enabled,
    staleTime: 0,
    gcTime: 0,
  });

export const useStartLocalInstall = () =>
  useMutation({
    mutationFn: (v: {
      target: "docker" | "kubernetes";
      body: StartLocalInstallRequest;
    }) => opsApi.startLocalInstall(v.target, v.body),
    gcTime: 0,
  });

const INSTALL_POLL_MS = 1000;

/** Ход установки: опрос раз в секунду, пока задача не закончится. */
export const useInstallJob = (id: string | null) =>
  useQuery({
    queryKey: opsKeys.installJob(id ?? ""),
    queryFn: () => opsApi.installJob(id ?? ""),
    enabled: id !== null,
    staleTime: 0,
    gcTime: 0,
    refetchInterval: (query) =>
      query.state.data?.state === "running" || !query.state.data
        ? INSTALL_POLL_MS
        : false,
  });

/**
 * Поставленное из админки: строки таблицы раннеров получают по нему «Обновить»
 * и «Удалить установку», а установки без раннера идут отдельным блоком.
 */
export const useLocalInstances = (enabled = true) =>
  useQuery({
    queryKey: opsKeys.installInstances,
    queryFn: () => opsApi.localInstances(),
    enabled,
    refetchInterval: POLL_MS * 6,
  });

/** Перечитать установки, раннеров и сводку: после обновления меняются версия и состояние. */
export const useRefreshRunners = () => {
  const client = useQueryClient();
  return useCallback(() => {
    for (const queryKey of [
      opsKeys.installInstances,
      opsKeys.runners,
      opsKeys.runnerSummary,
    ])
      void client.invalidateQueries({ queryKey });
  }, [client]);
};

export const useUpgradeLocalInstance = () =>
  useMutation({
    mutationFn: (v: { target: "docker" | "kubernetes"; name: string }) =>
      opsApi.upgradeLocalInstance(v.target, v.name),
    gcTime: 0,
  });

export const useRemoveLocalInstance = () => {
  const invalidate = useInvalidate();
  return useMutation({
    mutationFn: (v: { target: "docker" | "kubernetes"; name: string }) =>
      opsApi.removeLocalInstance(v.target, v.name),
    onSuccess: () => {
      invalidate(
        opsKeys.installInstances,
        opsKeys.runners,
        opsKeys.runnerSummary,
      );
    },
  });
};

export const useSshCapability = (enabled: boolean) =>
  useQuery({
    queryKey: opsKeys.sshCapability,
    queryFn: () => opsApi.sshCapability(),
    enabled,
    staleTime: 0,
    gcTime: 0,
  });

/** Пароль и ключ не попадают в кэш: мутации с секретом живут без gcTime. */
export const useSshProbe = () =>
  useMutation({
    mutationFn: (body: SshProbeRequest) => opsApi.sshProbe(body),
    gcTime: 0,
  });

export const useSshConfirm = () =>
  useMutation({
    mutationFn: (v: { sessionId: string; fingerprint: string }) =>
      opsApi.sshConfirm(v.sessionId, v.fingerprint),
    gcTime: 0,
  });

export const useSshInstall = () =>
  useMutation({
    mutationFn: (v: {
      sessionId: string;
      body: { name: string; install_docker: boolean };
    }) => opsApi.sshInstall(v.sessionId, v.body),
    gcTime: 0,
  });

export const useSshCredentials = (enabled: boolean) =>
  useQuery({
    queryKey: opsKeys.sshCredentials,
    queryFn: () => opsApi.sshCredentials(),
    enabled,
    staleTime: 0,
    gcTime: 0,
  });

export const useSshDeleteCredential = () => {
  const invalidate = useInvalidate();
  return useMutation({
    mutationFn: (id: string) => opsApi.sshDeleteCredential(id),
    onSuccess: () => {
      invalidate(opsKeys.sshCredentials);
    },
  });
};

export const useSshRunSaved = () =>
  useMutation({
    mutationFn: (v: { id: string; action: "update" | "reinstall" }) =>
      opsApi.sshRunSaved(v.id, v.action),
    gcTime: 0,
  });
