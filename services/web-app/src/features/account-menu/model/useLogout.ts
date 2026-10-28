import { useCallback, useState } from "react";
import { useQueryClient } from "@tanstack/react-query";
import { useNavigate } from "react-router";
import { i18n, toast } from "@shared/lib";
import {
  clearSessionEnded,
  clearUserScopedCache,
  sessionApi,
  sessionKeys,
  useRefreshSession,
  type Bootstrap,
} from "@entities/session";

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
  const navigate = useNavigate();
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
    clearSessionEnded();
    await clearUserScopedCache(client);
    // Явный выход ведёт на чистый /login без ?next: адрес прежнего человека
    // не должен достаться следующему. Пока bootstrap не обновился, помечаем
    // его анонимным, иначе шлюз вернул бы вошедшего с /login обратно на главную.
    client.setQueryData<Bootstrap>(sessionKeys.bootstrap(), (old) =>
      old ? { ...old, user: null, csrf_token: null } : old,
    );
    void navigate("/login", { replace: true });
    try {
      await refresh();
    } finally {
      setPending(false);
    }
  }, [client, navigate, refresh]);

  return { logout, pending };
};
