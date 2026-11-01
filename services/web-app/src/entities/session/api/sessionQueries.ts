import {
  useQuery,
  useQueryClient,
  type QueryClient,
} from "@tanstack/react-query";
import { useCallback, useEffect, useRef } from "react";
import { setCsrfToken } from "@shared/api";
import { clearSessionEnded } from "../lib/sessionEnded";
import { sessionApi } from "./sessionApi";
import type { Bootstrap, Capabilities } from "./schemas";

export const sessionKeys = {
  all: ["session"] as const,
  bootstrap: () => [...sessionKeys.all, "bootstrap"] as const,
};

/**
 * Состояние сессии: режим, мастер первого запуска, способы входа, пользователь,
 * возможности. Без повторов: 401 на этом запросе не бывает, а недоступный сервер
 * показывает ServerUnavailable с кнопкой «Повторить», а не вечный спиннер.
 */
export const useBootstrap = () =>
  useQuery<Bootstrap>({
    queryKey: sessionKeys.bootstrap(),
    queryFn: () => sessionApi.bootstrap(),
    retry: false,
    staleTime: 60_000,
  });

export type CapabilitiesState = {
  isLoading: boolean;
  // null, пока bootstrap не пришёл: решать по догадке нельзя.
  capabilities: Capabilities | null;
  has: (name: keyof Capabilities) => boolean;
  // Возможности точно нет: bootstrap пришёл и говорит «нет». Пока он не пришёл,
  // ответ false, чтобы локальные кнопки не пропадали из-за недозагрузки.
  lacks: (name: keyof Capabilities) => boolean;
};

export const useCapabilities = (): CapabilitiesState => {
  const { data, isLoading } = useBootstrap();
  const capabilities = data?.capabilities ?? null;
  const has = useCallback(
    (name: keyof Capabilities) => capabilities?.[name] === true,
    [capabilities],
  );
  const lacks = useCallback(
    (name: keyof Capabilities) => capabilities !== null && !capabilities[name],
    [capabilities],
  );
  return { isLoading, capabilities, has, lacks };
};

/** Обновить bootstrap: после входа, выхода и 401. */
export const useRefreshSession = () => {
  const client = useQueryClient();
  return useCallback(
    () => client.invalidateQueries({ queryKey: sessionKeys.bootstrap() }),
    [client],
  );
};

/**
 * Убрать из памяти всё, что принадлежало прежнему пользователю: CSRF-токен,
 * запросы (кроме сессии, её обновит шлюз) и мутации. Иначе следующий человек в
 * той же вкладке увидел бы чужие проекты, пока запросы не перезагрузятся.
 */
export const clearUserScopedCache = async (
  client: QueryClient,
): Promise<void> => {
  setCsrfToken(null);
  await client.cancelQueries();
  client.removeQueries({
    predicate: (query) => query.queryKey[0] !== sessionKeys.all[0],
  });
  client.getMutationCache().clear();
};

/**
 * Следит за пользователем в bootstrap: если вошедший человек исчез (сессия
 * истекла, отозвана, выход) или сменился другим, чистит кэш прежнего. Покрывает
 * пути, где useLogout не вызывался.
 */
export const useSessionIdentityGuard = (): void => {
  const client = useQueryClient();
  const { data } = useBootstrap();
  const userId = data ? (data.user?.id ?? null) : undefined;
  const previous = useRef<string | null | undefined>(undefined);
  useEffect(() => {
    if (userId === undefined) return;
    const was = previous.current;
    previous.current = userId;
    if (was != null && was !== userId) {
      void clearUserScopedCache(client);
    }
  }, [client, userId]);
  // Свежий bootstrap с пользователем: сессия жива (в том числе после csrf_failed).
  const signedIn = data?.user != null;
  useEffect(() => {
    if (signedIn) clearSessionEnded();
  }, [data, signedIn]);
};
