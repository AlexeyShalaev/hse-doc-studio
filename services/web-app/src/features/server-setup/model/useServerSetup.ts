import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useCallback, useEffect, useState } from "react";
import { ApiError, failureCode, setCsrfToken } from "@shared/api";
import { useBootstrap, useRefreshSession } from "@entities/session";
import { serverSetupApi, type SetupSettingsBody } from "../api/serverSetupApi";
import {
  isOccupied,
  nextStep,
  prevStep,
  resumeStep,
  type SetupStepId,
} from "../lib/steps";

export const serverSetupKeys = {
  all: ["server-setup"] as const,
  status: () => [...serverSetupKeys.all, "status"] as const,
  settings: () => [...serverSetupKeys.all, "settings"] as const,
  environment: () => [...serverSetupKeys.all, "environment"] as const,
};

export type SetupFailure = { code: string };

const toFailure = (error: unknown): SetupFailure => ({
  code: failureCode(error),
});

/**
 * Состояние мастера первого запуска. Сервер хранит, что уже сделано, поэтому
 * после перезагрузки мастер продолжается с нужного шага, а не с начала. Шаг
 * «готово» живёт только в памяти: после завершения ручки мастера отвечают 404.
 */
export const useServerSetup = () => {
  const client = useQueryClient();
  const refresh = useRefreshSession();
  const bootstrap = useBootstrap().data;
  const isAdminSession = bootstrap?.user?.is_instance_admin === true;

  const [override, setOverride] = useState<SetupStepId | null>(null);
  const [finished, setFinished] = useState(false);

  const status = useQuery({
    queryKey: serverSetupKeys.status(),
    queryFn: () => serverSetupApi.status(),
    retry: false,
    enabled: !finished,
  });
  const statusData = status.data;
  const occupied = statusData ? isOccupied(statusData, isAdminSession) : false;
  const workable = statusData !== undefined && !occupied;

  const settings = useQuery({
    queryKey: serverSetupKeys.settings(),
    queryFn: () => serverSetupApi.settings(),
    retry: false,
    enabled:
      !finished &&
      isAdminSession &&
      statusData?.steps_done.includes("admin") === true,
    // Правки живут в форме; серверное значение не должно перебивать их фоном.
    staleTime: Infinity,
    refetchOnWindowFocus: false,
  });

  const resumed = statusData ? resumeStep(statusData) : null;
  const step: SetupStepId | null = finished
    ? "done"
    : (override ?? (workable ? resumed : null));

  const environment = useQuery({
    queryKey: serverSetupKeys.environment(),
    queryFn: () => serverSetupApi.environment(),
    retry: false,
    enabled: !finished && isAdminSession && step === "environment",
    refetchOnWindowFocus: false,
    staleTime: 0,
  });

  // Мастер завершён в другой вкладке: его ручки отвечают 404, шлюз уведёт дальше.
  const closedElsewhere =
    status.error instanceof ApiError && status.error.status === 404;
  useEffect(() => {
    if (closedElsewhere) void refresh();
  }, [closedElsewhere, refresh]);

  const [failure, setFailure] = useState<SetupFailure | null>(null);
  const clearFailure = useCallback(() => {
    setFailure(null);
  }, []);

  const go = useCallback((target: SetupStepId) => {
    setFailure(null);
    setOverride(target);
  }, []);
  const forward = useCallback(() => {
    if (step) go(nextStep(step));
  }, [go, step]);
  const back = useCallback(() => {
    if (step) go(prevStep(step));
  }, [go, step]);

  const createAdmin = useMutation({
    mutationFn: serverSetupApi.createAdmin,
    onSuccess: async (res) => {
      setCsrfToken(res.csrf_token);
      await Promise.all([
        refresh(),
        client.invalidateQueries({ queryKey: serverSetupKeys.status() }),
      ]);
      go("registration");
    },
    onError: async (error) => {
      const next = toFailure(error);
      setFailure(next);
      // Опоздали: админ уже создан другим. Статус покажет нейтральный экран.
      if (next.code === "setup_already_done" || next.code === "csrf_failed") {
        await Promise.all([
          refresh(),
          client.invalidateQueries({ queryKey: serverSetupKeys.status() }),
        ]);
      }
    },
  });

  const applySettings = useMutation({
    mutationFn: (body: SetupSettingsBody) => serverSetupApi.applySettings(body),
    onSuccess: async () => {
      await client.invalidateQueries({ queryKey: serverSetupKeys.status() });
      go("environment");
    },
    onError: (error) => {
      setFailure(toFailure(error));
    },
  });

  const complete = useMutation({
    mutationFn: () => serverSetupApi.complete(),
    onSuccess: () => {
      setFinished(true);
      setFailure(null);
    },
    onError: (error) => {
      setFailure(toFailure(error));
    },
  });

  /** Мастер закрыт: bootstrap теперь «готово», шлюз сам уведёт в приложение. */
  const open = useCallback(() => refresh(), [refresh]);

  return {
    step,
    status,
    occupied,
    isAdminSession,
    user: bootstrap?.user ?? null,
    passwordMinLength: bootstrap?.auth.password_min_length ?? 10,
    smtpEnabled: bootstrap?.auth.smtp_enabled ?? false,
    settings,
    environment,
    failure,
    clearFailure,
    go,
    forward,
    back,
    createAdmin,
    applySettings,
    complete,
    open,
  };
};

export type ServerSetupModel = ReturnType<typeof useServerSetup>;
