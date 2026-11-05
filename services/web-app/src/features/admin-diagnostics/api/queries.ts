import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import type {
  AcceptDiagnosticsRequest,
  UpdateDiagnosticsThresholdsRequest,
} from "@entities/session";
import { diagnosticsApi } from "./diagnosticsApi";

export const diagnosticsKeys = {
  overview: ["admin", "diagnostics"] as const,
};

/** Состояние проверок: фоновый проход идёт раз в несколько минут, опрос раз в 30 секунд. */
export const useDiagnostics = () =>
  useQuery({
    queryKey: diagnosticsKeys.overview,
    queryFn: () => diagnosticsApi.overview(),
    staleTime: 0,
    refetchInterval: 30_000,
  });

export const useRunDiagnostics = () => {
  const client = useQueryClient();
  return useMutation({
    mutationFn: (check: string | null) => diagnosticsApi.run(check),
    onSuccess: (saved) => {
      client.setQueryData(diagnosticsKeys.overview, saved);
    },
  });
};

export const useSaveThresholds = () => {
  const client = useQueryClient();
  return useMutation({
    mutationFn: (body: UpdateDiagnosticsThresholdsRequest) =>
      diagnosticsApi.saveThresholds(body),
    onSuccess: (saved) => {
      client.setQueryData(diagnosticsKeys.overview, saved);
    },
  });
};

/** Для меню и баннеров: тот же ответ, что у страницы, но без частого опроса. */
export const useDiagnosticsQuiet = () =>
  useQuery({
    queryKey: diagnosticsKeys.overview,
    queryFn: () => diagnosticsApi.overview(),
    staleTime: 30_000,
    refetchInterval: 60_000,
  });

export const useAcceptWarning = () => {
  const client = useQueryClient();
  return useMutation({
    mutationFn: (arg: { check: string; body: AcceptDiagnosticsRequest }) =>
      diagnosticsApi.accept(arg.check, arg.body),
    onSuccess: (saved) => {
      client.setQueryData(diagnosticsKeys.overview, saved);
      // Статус обновления и меню читают принятие из своих ответов.
      void client.invalidateQueries({ queryKey: ["admin", "updates"] });
    },
  });
};

export const useRevokeAcceptance = () => {
  const client = useQueryClient();
  return useMutation({
    mutationFn: (check: string) => diagnosticsApi.revoke(check),
    onSuccess: (saved) => {
      client.setQueryData(diagnosticsKeys.overview, saved);
      void client.invalidateQueries({ queryKey: ["admin", "updates"] });
    },
  });
};
