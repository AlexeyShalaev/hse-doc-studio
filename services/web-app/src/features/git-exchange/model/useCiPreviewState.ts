import { useEffect, useMemo, useState } from "react";
import { useCiPreview } from "@entities/git-remote";
import {
  describeGitError,
  type CiPreview,
  type CiRequest,
} from "@entities/git-sync";
import { ciProblems, toCiRequest, type CiOptions } from "./ciOptions";

// Пока человек щёлкает по настройкам, на сервер уходит только последний выбор.
export const CI_PREVIEW_DEBOUNCE_MS = 250;

export type CiPreviewState = {
  /** Последний полученный файл; остаётся на экране, пока считается новый. */
  preview: CiPreview | null;
  request: CiRequest;
  isLoading: boolean;
  error: string | null;
  retry: () => void;
};

// Предпросмотр файла автосборки: пересчитывается при каждом изменении настроек.
export const useCiPreviewState = (
  projectId: string,
  options: CiOptions,
  enabled: boolean,
): CiPreviewState => {
  const mutation = useCiPreview();
  const { mutate } = mutation;
  const request = useMemo(() => toCiRequest(options), [options]);
  const valid = ciProblems(options).length === 0;

  const [preview, setPreview] = useState<CiPreview | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [attempt, setAttempt] = useState(0);

  useEffect(() => {
    if (!enabled || !valid) return;
    const timer = setTimeout(() => {
      mutate(
        { projectId, params: request },
        {
          onSuccess: (data) => {
            setPreview(data);
            setError(null);
          },
          onError: (caught) => {
            setError(describeGitError(caught, ""));
          },
        },
      );
    }, CI_PREVIEW_DEBOUNCE_MS);
    return () => {
      clearTimeout(timer);
    };
  }, [enabled, valid, mutate, projectId, request, attempt]);

  return {
    preview,
    request,
    isLoading: valid && mutation.isPending,
    error,
    retry: () => {
      setAttempt((current) => current + 1);
    },
  };
};
