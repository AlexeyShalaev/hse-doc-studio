import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { updatesApi } from "./updatesApi";
import type { UpdateSettings } from "./schemas";

export const updateKeys = {
  status: ["admin", "updates", "status"] as const,
  runs: (page: number) => ["admin", "updates", "runs", page] as const,
  runsAll: ["admin", "updates", "runs"] as const,
};

export const RUNS_PAGE_SIZE = 10;
/** Пока идёт запуск, статус и история обновляются чаще. */
const POLL_BUSY_MS = 3000;
const POLL_IDLE_MS = 20000;

export const useUpdateStatus = () =>
  useQuery({
    queryKey: updateKeys.status,
    queryFn: () => updatesApi.status(),
    staleTime: 0,
    // Во время обновления api гаснет на минуты: ошибки опроса не должны сбрасывать экран.
    retry: false,
    refetchInterval: (query) =>
      query.state.data?.active_run ? POLL_BUSY_MS : POLL_IDLE_MS,
  });

export const useUpdateRuns = (page: number, busy: boolean) =>
  useQuery({
    queryKey: updateKeys.runs(page),
    queryFn: () => updatesApi.runs(RUNS_PAGE_SIZE, page * RUNS_PAGE_SIZE),
    staleTime: 0,
    retry: false,
    refetchInterval: busy ? POLL_BUSY_MS : POLL_IDLE_MS,
  });

const useRefresh = () => {
  const client = useQueryClient();
  return () => {
    void client.invalidateQueries({ queryKey: updateKeys.status });
    void client.invalidateQueries({ queryKey: updateKeys.runsAll });
  };
};

export const useSaveUpdateSettings = () => {
  const client = useQueryClient();
  return useMutation({
    mutationFn: (body: UpdateSettings) => updatesApi.saveSettings(body),
    onSuccess: (status) => {
      client.setQueryData(updateKeys.status, status);
    },
  });
};

export const useCheckUpdates = () => {
  const client = useQueryClient();
  return useMutation({
    mutationFn: () => updatesApi.check(),
    onSuccess: (status) => {
      client.setQueryData(updateKeys.status, status);
    },
  });
};

export const useStartUpdate = () => {
  const refresh = useRefresh();
  return useMutation({
    mutationFn: (arg: { version: string | null; acceptRisk: boolean }) =>
      updatesApi.start(arg.version, arg.acceptRisk),
    onSuccess: refresh,
  });
};

export const useRollbackUpdate = () => {
  const refresh = useRefresh();
  return useMutation({
    mutationFn: (restoreDb: boolean) => updatesApi.rollback(restoreDb),
    onSuccess: refresh,
  });
};

export const useCancelUpdate = () => {
  const refresh = useRefresh();
  return useMutation({
    mutationFn: (id: string) => updatesApi.cancel(id),
    onSuccess: refresh,
  });
};
