import { useEffect, useRef } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  adminRunnerDiskApi,
  runnerDiskApi,
  type RunnerDiskScope,
} from "./runnerDiskApi";
import { runnerKeys } from "./runnerQueries";
import {
  RUNNER_DISK_ACTIVE_POLL_MS,
  RUNNER_DISK_IDLE_POLL_MS,
  isDiskCommandActive,
  isRunnerDiskBusy,
} from "../lib/runnerDiskLib";
import type {
  RunnerDiskAutoRequest,
  RunnerDiskCleanupRequest,
  RunnerDiskCommand,
  RunnerDiskView,
} from "../model/runnerDisk.schema";

export const runnerDiskKeys = {
  all: ["runner-disk"] as const,
  view: (scope: RunnerDiskScope, runnerId: string) =>
    [...runnerDiskKeys.all, scope, runnerId] as const,
  summary: () => [...runnerDiskKeys.all, "summary"] as const,
};

/**
 * Очистки, запущенные из этой вкладки: их итог считается «на глазах», даже если опрос не застал
 * команду незакрытой (раннер управился между двумя опросами).
 */
const startedHere = new Set<string>();

export type UseRunnerDiskOptions = {
  /** Опрос только при открытом диалоге: закрытый диалог не держит запрос. */
  enabled?: boolean | undefined;
  /**
   * Команда очистки закрылась у этого экрана на глазах (итог, остановка, потеря). Фича
   * перечитывает по нему свои списки: у строк раннеров меняется поле `disk`.
   */
  onCommandSettled?: ((command: RunnerDiskCommand) => void) | undefined;
};

/**
 * Диск раннера (`GET .../disk`). Раз в 2 с, пока команда не закрыта или идёт замер, иначе
 * раз в 30 с (9.3). Когда очистка закрылась, сводка «Хранилища» и «Мои раннеры» перечитываются.
 */
export const useRunnerDisk = (
  scope: RunnerDiskScope,
  runnerId: string | null,
  options: UseRunnerDiskOptions = {},
) => {
  const client = useQueryClient();
  const query = useQuery({
    queryKey: runnerDiskKeys.view(scope, runnerId ?? ""),
    queryFn: () => runnerDiskApi(scope).get(runnerId ?? ""),
    enabled: runnerId !== null && (options.enabled ?? true),
    staleTime: 0,
    refetchInterval: (q) =>
      isRunnerDiskBusy(q.state.data)
        ? RUNNER_DISK_ACTIVE_POLL_MS
        : RUNNER_DISK_IDLE_POLL_MS,
  });

  const command = query.data?.command ?? null;
  const seen = useRef<{ id: string; active: boolean } | null>(null);
  const onSettled = useRef(options.onCommandSettled);
  useEffect(() => {
    onSettled.current = options.onCommandSettled;
  });
  useEffect(() => {
    if (command === null) {
      seen.current = null;
      return;
    }
    const active = isDiskCommandActive(command);
    const before = seen.current;
    seen.current = { id: command.id, active };
    if (active) return;
    const watched =
      (before?.id === command.id && before.active) ||
      startedHere.has(command.id);
    if (!watched) return;
    startedHere.delete(command.id);
    void client.invalidateQueries({ queryKey: runnerDiskKeys.summary() });
    if (scope === "account") {
      void client.invalidateQueries({ queryKey: runnerKeys.mine() });
    }
    onSettled.current?.(command);
  }, [client, command, scope]);

  return query;
};

/** Положить команду в кэш вида сразу, не дожидаясь опроса: полоса хода появляется мгновенно. */
const putCommand = (
  view: RunnerDiskView | undefined,
  command: RunnerDiskCommand,
): RunnerDiskView | undefined => {
  if (!view) return view;
  return command.kind === "disk.measure"
    ? { ...view, measuring: true }
    : { ...view, command };
};

/** Ответ команды сразу в кэш вида, затем перечитать вид. */
const useOnCommand = (scope: RunnerDiskScope, runnerId: string) => {
  const client = useQueryClient();
  const key = runnerDiskKeys.view(scope, runnerId);
  return (command: RunnerDiskCommand) => {
    if (command.kind === "disk.cleanup") startedHere.add(command.id);
    client.setQueryData<RunnerDiskView>(key, (view) =>
      putCommand(view, command),
    );
    void client.invalidateQueries({ queryKey: key });
  };
};

/** «Обновить»: поставить `disk.measure`. */
export const useRefreshRunnerDisk = (
  scope: RunnerDiskScope,
  runnerId: string,
) =>
  useMutation({
    mutationFn: () => runnerDiskApi(scope).refresh(runnerId),
    onSuccess: useOnCommand(scope, runnerId),
  });

/** Запустить очистку целей; откат только с `include_rollback` и только там, где можно. */
export const useStartRunnerDiskCleanup = (
  scope: RunnerDiskScope,
  runnerId: string,
) =>
  useMutation({
    mutationFn: (body: RunnerDiskCleanupRequest) =>
      runnerDiskApi(scope).cleanup(runnerId, body),
    onSuccess: useOnCommand(scope, runnerId),
  });

/** «Остановить после текущего шага». */
export const useCancelRunnerDiskCleanup = (
  scope: RunnerDiskScope,
  runnerId: string,
) =>
  useMutation({
    mutationFn: (commandId: string) =>
      runnerDiskApi(scope).cancel(runnerId, commandId),
    onSuccess: useOnCommand(scope, runnerId),
  });

/** Сводка дисков общих раннеров для блока «Где ещё освободить место» (только админка). */
export const useRunnerDiskSummary = (options: { enabled?: boolean } = {}) =>
  useQuery({
    queryKey: runnerDiskKeys.summary(),
    queryFn: () => adminRunnerDiskApi.summary(),
    enabled: options.enabled ?? true,
    staleTime: 30_000,
  });

/** Сохранить автоочистку общего раннера (только админка): ответ сразу в кэш вида. */
export const useSetRunnerDiskAuto = (runnerId: string) => {
  const client = useQueryClient();
  const key = runnerDiskKeys.view("admin", runnerId);
  return useMutation({
    mutationFn: (body: RunnerDiskAutoRequest) =>
      adminRunnerDiskApi.setAuto(runnerId, body),
    onSuccess: (auto) => {
      client.setQueryData<RunnerDiskView>(key, (view) =>
        view ? { ...view, auto } : view,
      );
    },
  });
};
