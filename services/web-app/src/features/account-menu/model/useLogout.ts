import { useCallback, useState } from "react";
import { useQueryClient } from "@tanstack/react-query";
import { setCsrfToken } from "@shared/api";
import { i18n, toast } from "@shared/lib";
import { sessionApi, sessionKeys, useRefreshSession } from "@entities/session";

/**
 * Выход. Сервер закрывает сессию, после чего из памяти уходит всё, что принадлежало
 * этому пользователю: кэш запросов целиком (кроме bootstrap, его обновит шлюз) и
 * CSRF-токен. Иначе следующий человек в той же вкладке увидел бы чужие проекты,
 * пока запросы не перезагрузятся.
 *
 * Если сервер выход не подтвердил, ничего не чистим: сессия жива, а пустой кэш при
 * живой сессии только мигал бы спиннерами.
 */
export const useLogout = () => {
  const client = useQueryClient();
  const refresh = useRefreshSession();
  const [pending, setPending] = useState(false);

  const logout = useCallback(async () => {
    setPending(true);
    try {
      await sessionApi.logout();
    } catch {
      toast.error(i18n.t("appChrome:accountMenu.logoutFailed"));
      setPending(false);
      return;
    }
    setCsrfToken(null);
    await client.cancelQueries();
    client.removeQueries({
      predicate: (query) => query.queryKey[0] !== sessionKeys.all[0],
    });
    client.getMutationCache().clear();
    try {
      await refresh();
    } finally {
      setPending(false);
    }
  }, [client, refresh]);

  return { logout, pending };
};
