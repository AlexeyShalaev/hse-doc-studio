import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { backupsApi } from "./backupsApi";
import type { DestinationBody, SettingsBody } from "./schemas";

export const backupKeys = {
  all: ["admin", "backups"] as const,
  status: ["admin", "backups", "status"] as const,
  destinations: ["admin", "backups", "destinations"] as const,
  runs: (page: number) => ["admin", "backups", "runs", page] as const,
  runsAll: ["admin", "backups", "runs"] as const,
  stored: (id: string) => ["admin", "backups", "stored", id] as const,
};

export const RUNS_PAGE_SIZE = 10;
/** Пока идёт запуск, статус и история обновляются чаще. */
const POLL_BUSY_MS = 2000;
const POLL_IDLE_MS = 15000;

export const useBackupStatus = () =>
  useQuery({
    queryKey: backupKeys.status,
    queryFn: () => backupsApi.status(),
    staleTime: 0,
    refetchInterval: (query) =>
      query.state.data?.running ? POLL_BUSY_MS : POLL_IDLE_MS,
  });

export const useDestinations = () =>
  useQuery({
    queryKey: backupKeys.destinations,
    queryFn: () => backupsApi.destinations(),
    staleTime: 0,
  });

export const useBackupRuns = (page: number, busy: boolean) =>
  useQuery({
    queryKey: backupKeys.runs(page),
    queryFn: () => backupsApi.runs(RUNS_PAGE_SIZE, page * RUNS_PAGE_SIZE),
    staleTime: 0,
    refetchInterval: busy ? POLL_BUSY_MS : POLL_IDLE_MS,
  });

export const useStoredBackups = (id: string, enabled: boolean) =>
  useQuery({
    queryKey: backupKeys.stored(id),
    queryFn: () => backupsApi.stored(id),
    enabled,
    staleTime: 0,
    retry: false,
  });

export const useSaveSettings = () => {
  const client = useQueryClient();
  return useMutation({
    mutationFn: (body: SettingsBody) => backupsApi.saveSettings(body),
    onSuccess: (status) => {
      client.setQueryData(backupKeys.status, status);
    },
  });
};

export const useSaveDestination = () => {
  const client = useQueryClient();
  return useMutation({
    mutationFn: (input: { id: string | null; body: DestinationBody }) =>
      input.id
        ? backupsApi.updateDestination(input.id, input.body)
        : backupsApi.createDestination(input.body),
    onSuccess: () => {
      void client.invalidateQueries({ queryKey: backupKeys.destinations });
      void client.invalidateQueries({ queryKey: backupKeys.status });
    },
  });
};

export const useDeleteDestination = () => {
  const client = useQueryClient();
  return useMutation({
    mutationFn: (id: string) => backupsApi.deleteDestination(id),
    onSuccess: () => {
      void client.invalidateQueries({ queryKey: backupKeys.destinations });
      void client.invalidateQueries({ queryKey: backupKeys.status });
    },
  });
};

export const useTestDestination = () => {
  const client = useQueryClient();
  return useMutation({
    mutationFn: (id: string) => backupsApi.testSaved(id),
    onSettled: () => {
      void client.invalidateQueries({ queryKey: backupKeys.destinations });
    },
  });
};

export const useStartBackup = () => {
  const client = useQueryClient();
  return useMutation({
    mutationFn: (destinationId: string | null) =>
      backupsApi.start(destinationId),
    onSuccess: () => {
      void client.invalidateQueries({ queryKey: backupKeys.status });
      void client.invalidateQueries({ queryKey: backupKeys.runsAll });
    },
  });
};

export const useDeleteStored = () => {
  const client = useQueryClient();
  return useMutation({
    mutationFn: (input: { id: string; backupId: string }) =>
      backupsApi.deleteStored(input.id, input.backupId),
    onSuccess: (_void, input) => {
      void client.invalidateQueries({ queryKey: backupKeys.stored(input.id) });
      void client.invalidateQueries({ queryKey: backupKeys.runsAll });
    },
  });
};
