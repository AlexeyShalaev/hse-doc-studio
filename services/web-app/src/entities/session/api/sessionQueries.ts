import { useQuery, useQueryClient } from "@tanstack/react-query";
import { useCallback } from "react";
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
