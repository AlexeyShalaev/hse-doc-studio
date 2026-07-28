import { useCallback, useState } from "react";
import { keepPreviousData, useQuery } from "@tanstack/react-query";
import { setupApi, setupKeys, type ProbeFolderResult } from "@entities/setup";
import { detectHostOs, homesRoot, isAbsoluteHostPath } from "../lib/hostPath";

export type HostBrowserState = {
  /** Путь, который сейчас показан и который применится при подтверждении. */
  path: string;
  probe: ProbeFolderResult | null;
  isLoading: boolean;
  /** Путь не полный — сервер даже не звали. */
  isRelative: boolean;
  goTo: (path: string) => void;
};

/** Столько живёт ответ про уже посещённую папку: подъём назад должен быть мгновенным. */
const FOLDER_CACHE_MS = 60_000;

/**
 * Обзор файловой системы ХОСТА. Каждый шаг — одноразовый контейнер с
 * бинд-маунтом, то есть переход стоит секунду-полторы.
 *
 * Отсюда и кэш: путь наверх пользователь проходит теми же папками, которыми
 * спускался, и платить за них второй раз незачем. Гонку запросов TanStack Query
 * решает сам — отменять тут всё равно нечего, время уходит внутри докера.
 */
export const useHostBrowser = (): HostBrowserState => {
  const [path, setPath] = useState(() => homesRoot(detectHostOs()));

  const trimmed = path.trim();
  const isRelative = trimmed !== "" && !isAbsoluteHostPath(trimmed);
  const enabled = trimmed !== "" && !isRelative;

  const query = useQuery<ProbeFolderResult>({
    queryKey: setupKeys.folder(trimmed),
    queryFn: () => setupApi.probeFolder(trimmed),
    enabled,
    retry: false,
    staleTime: FOLDER_CACHE_MS,
    // Переход стоит запуска контейнера, полторы секунды. Без этого список на
    // всё это время пустел, и человек видел не «грузится», а «папка пустая» —
    // пятое, необъявленное состояние. Прежнее содержимое притушено крутилкой в
    // крошках, поэтому за актуальное его не примешь.
    placeholderData: keepPreviousData,
  });

  const goTo = useCallback((next: string) => {
    setPath(next);
  }, []);

  return {
    path,
    probe: enabled ? (query.data ?? null) : null,
    isLoading: enabled && query.isFetching,
    isRelative,
    goTo,
  };
};
