import { useMutation, useQuery } from "@tanstack/react-query";
import {
  setupApi,
  type ApplySetupResult,
  type ProbeFolderResult,
  type SetupEnvironment,
  type SetupStatus,
} from "./setupApi";

export const setupKeys = {
  all: ["setup"] as const,
  status: () => [...setupKeys.all, "status"] as const,
  // Обзор папок хоста ключуется путём: подъём назад проходит по уже
  // посещённым каталогам, и второй раз платить за контейнер незачем.
  folder: (path: string) => [...setupKeys.all, "folder", path] as const,
  environment: () => [...setupKeys.all, "environment"] as const,
};

/**
 * Состояние установки. Спрашивается один раз при открытии приложения и НЕ
 * опрашивается по таймеру: измениться оно может ровно одним способом — через
 * мастер, а тот пересоздаёт контейнер, после чего страница и так перезагружается.
 *
 * `retry: false` намеренно: пока бэкенд старой версии не знает этой ручки,
 * повторять запрос бессмысленно, а стартовый экран не должен на этом висеть.
 */
export const useSetupStatus = () =>
  useQuery<SetupStatus>({
    queryKey: setupKeys.status(),
    queryFn: () => setupApi.status(),
    retry: false,
    staleTime: Infinity,
  });

/**
 * Сведения о машине и параметрах запуска. Меняться в течение сеанса они не
 * могут: движок посреди работы не подменяют, а свою конфигурацию мы сменим
 * только пересозданием, которое убьёт этот процесс вместе со страницей.
 */
export const useSetupEnvironment = () =>
  useQuery<SetupEnvironment>({
    queryKey: setupKeys.environment(),
    queryFn: () => setupApi.environment(),
    retry: false,
    staleTime: Infinity,
  });

export const useProbeFolder = () =>
  useMutation<ProbeFolderResult, Error, string>({
    mutationFn: (hostPath: string) => setupApi.probeFolder(hostPath),
  });

export const useApplySetup = () =>
  useMutation<ApplySetupResult, Error, string>({
    mutationFn: (hostPath: string) => setupApi.apply(hostPath),
  });
