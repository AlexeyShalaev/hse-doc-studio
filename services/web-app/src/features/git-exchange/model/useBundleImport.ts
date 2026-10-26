import { useCallback, useEffect, useRef, useState } from "react";
import { useQueryClient } from "@tanstack/react-query";
import { useTranslation } from "react-i18next";
import {
  invalidateAfterSync,
  readGitError,
  useCancelOperation,
  useImportBundle,
  useOperation,
  type GitOperation,
  type SyncResult,
} from "@entities/git-sync";
import { flushPendingSaves } from "@shared/lib";
import { ApiError } from "@shared/api";
import {
  NETWORK_FAILED_CODE,
  SAVE_FAILED_CODE,
  type BundleFailure,
} from "./bundleFailure";

// Где находится импорт. Итог не хранится отдельно: он считается из операции
// на сервере, поэтому после «не вышло» окно просто возвращается к выбору файла.
export type ImportStage = "choose" | "uploading" | "running" | "done";

export type BundleImport = {
  stage: ImportStage;
  /** Сколько файла уже ушло на сервер, 0..100; null, если длина неизвестна. */
  percent: number | null;
  operation: GitOperation | undefined;
  /** Итог слияния, когда импорт закончился успешно. */
  result: SyncResult | null;
  failure: BundleFailure | null;
  /** Операция отменена: файл можно выбрать заново. */
  cancelled: boolean;
  /** Не удалось узнать ход операции (обрыв связи). */
  lost: boolean;
  isCancelling: boolean;
  start: (file: File, password: string) => Promise<void>;
  cancel: () => void;
  /** Забыть отказ (человек поменял файл или пароль). */
  dismissFailure: () => void;
  /** Вернуться к выбору файла и забыть всё, что было. */
  reset: () => void;
  retryLookup: () => void;
};

const isSyncResult = (
  result: GitOperation["result"] | undefined,
): result is SyncResult =>
  !!result && typeof (result as { outcome?: unknown }).outcome === "string";

const isCanceled = (error: unknown): boolean =>
  error instanceof Error &&
  (error.name === "CanceledError" ||
    (error as { code?: string }).code === "ERR_CANCELED");

// Загрузка файла, запуск слияния и слежение за ним. Пока файл едет, процент
// берётся из запроса; после этого за дело отвечает операция на сервере.
export const useBundleImport = (projectId: string): BundleImport => {
  const { t } = useTranslation("gitExchange");
  const queryClient = useQueryClient();
  const importBundle = useImportBundle();
  const cancelOperation = useCancelOperation();

  const [uploading, setUploading] = useState(false);
  const [percent, setPercent] = useState<number | null>(null);
  const [operationId, setOperationId] = useState<string | null>(null);
  const [startFailure, setStartFailure] = useState<BundleFailure | null>(null);
  const abortRef = useRef<AbortController | null>(null);
  const startingRef = useRef(false);
  const settledRef = useRef<string | null>(null);

  const operationQuery = useOperation(operationId);
  const operation = operationQuery.data;

  // Слияние поменяло файлы, версии, подписи и формы: один раз на операцию.
  const succeededId = operation?.status === "succeeded" ? operation.id : null;
  useEffect(() => {
    if (succeededId === null || settledRef.current === succeededId) return;
    settledRef.current = succeededId;
    invalidateAfterSync(queryClient, projectId);
  }, [projectId, queryClient, succeededId]);

  const start = useCallback(
    async (file: File, password: string): Promise<void> => {
      if (startingRef.current) return;
      startingRef.current = true;
      setStartFailure(null);
      setOperationId(null);
      setPercent(null);
      setUploading(true);
      const controller = new AbortController();
      abortRef.current = controller;
      try {
        // Правки в редакторах дописываются с задержкой; слияние без них вышло
        // бы неполным, а сами они потом легли бы поверх слитых файлов.
        const flushed = await flushPendingSaves();
        if (flushed.failed > 0) {
          setStartFailure({
            code: SAVE_FAILED_CODE,
            detail: t("failure.save_failed.text"),
          });
          return;
        }
        const started = await importBundle.mutateAsync({
          projectId,
          file,
          ...(password === "" ? {} : { password }),
          options: { onProgress: setPercent, signal: controller.signal },
        });
        setOperationId(started.operation_id);
      } catch (error) {
        if (isCanceled(error)) return;
        const body = readGitError(error);
        setStartFailure(
          body
            ? { code: body.code, detail: body.detail, params: body }
            : error instanceof ApiError
              ? { code: "git_error", detail: error.detail }
              : { code: NETWORK_FAILED_CODE, detail: "" },
        );
      } finally {
        abortRef.current = null;
        startingRef.current = false;
        setUploading(false);
      }
    },
    [importBundle, projectId, t],
  );

  const cancel = useCallback((): void => {
    if (abortRef.current) {
      abortRef.current.abort();
      return;
    }
    if (operation?.status === "running") {
      cancelOperation.mutate(operation.id);
    }
  }, [cancelOperation, operation]);

  const reset = useCallback((): void => {
    setStartFailure(null);
    setOperationId(null);
    setPercent(null);
    settledRef.current = null;
  }, []);

  const operationFailure: BundleFailure | null =
    operation?.status === "failed"
      ? {
          code: operation.error?.code ?? "git_error",
          detail: operation.error?.detail ?? "",
        }
      : null;

  const stage: ImportStage = uploading
    ? "uploading"
    : operationId === null
      ? "choose"
      : operation === undefined
        ? "running"
        : operation.status === "running"
          ? "running"
          : operation.status === "succeeded"
            ? "done"
            : "choose";

  return {
    stage,
    percent,
    operation,
    result:
      operation?.status === "succeeded" && isSyncResult(operation.result)
        ? operation.result
        : null,
    failure: startFailure ?? operationFailure,
    cancelled: operation?.status === "cancelled",
    lost:
      operationId !== null && operation === undefined && operationQuery.isError,
    isCancelling: cancelOperation.isPending,
    start,
    cancel,
    dismissFailure: () => {
      setStartFailure(null);
      // Отказ операции лежит в самой операции: чтобы его забыть, отпускаем её.
      if (operation && operation.status !== "running") setOperationId(null);
    },
    reset,
    retryLookup: () => {
      void operationQuery.refetch();
    },
  };
};
