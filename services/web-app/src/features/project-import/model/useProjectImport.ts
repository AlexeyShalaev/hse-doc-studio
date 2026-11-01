import { useCallback, useRef, useState } from "react";
import { useQueryClient } from "@tanstack/react-query";
import { ApiError } from "@shared/api/client";
import { projectApi, projectKeys } from "@entities/project";
import type { ProjectImportResult } from "@entities/session";

export type ImportStage = "idle" | "uploading" | "done" | "failed";

export type ImportFailure = {
  /** Код ответа сервера (import_archive_unsafe, ...); network для обрыва связи. */
  code: string;
  /** Текст сервера на языке интерфейса: запасной, если для кода нет перевода. */
  detail: string;
};

const failureOf = (error: unknown): ImportFailure => {
  if (error instanceof ApiError) {
    return {
      code: error.status === 0 ? "network" : error.code,
      detail: error.detail,
    };
  }
  return { code: "network", detail: "" };
};

const isAbort = (error: unknown): boolean =>
  error instanceof Error &&
  (error.name === "CanceledError" || error.name === "AbortError");

// Загрузка архива проекта: ход отправки, итог или отказ. Прервать можно только отправку:
// после неё сервер уже распаковывает архив в одной транзакции и отменить это нечем.
export const useProjectImport = () => {
  const queryClient = useQueryClient();
  const controller = useRef<AbortController | null>(null);
  const [stage, setStage] = useState<ImportStage>("idle");
  const [percent, setPercent] = useState(0);
  const [result, setResult] = useState<ProjectImportResult | null>(null);
  const [failure, setFailure] = useState<ImportFailure | null>(null);

  const start = useCallback(
    async (file: File): Promise<void> => {
      const abort = new AbortController();
      controller.current = abort;
      setStage("uploading");
      setPercent(0);
      setFailure(null);
      try {
        const imported = await projectApi.importArchive(file, {
          signal: abort.signal,
          onProgress: setPercent,
        });
        setResult(imported);
        setStage("done");
        void queryClient.invalidateQueries({ queryKey: projectKeys.lists() });
      } catch (error) {
        if (isAbort(error)) {
          setStage("idle");
          return;
        }
        setFailure(failureOf(error));
        setStage("failed");
      } finally {
        controller.current = null;
      }
    },
    [queryClient],
  );

  const cancel = useCallback((): void => {
    controller.current?.abort();
  }, []);

  const reset = useCallback((): void => {
    setStage("idle");
    setPercent(0);
    setResult(null);
    setFailure(null);
  }, []);

  return { stage, percent, result, failure, start, cancel, reset };
};
