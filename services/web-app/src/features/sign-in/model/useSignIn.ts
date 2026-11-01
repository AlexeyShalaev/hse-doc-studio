import { useQueryClient } from "@tanstack/react-query";
import { useCallback, useState } from "react";
import { ApiError, setCsrfToken } from "@shared/api";
import { clearUserScopedCache, useRefreshSession } from "@entities/session";
import { signInApi, toLoginFailure } from "../api/signInApi";
import type { LoginFailure } from "../lib/loginErrors";

/**
 * Вход по паролю. После успеха токен CSRF уходит в транспорт, bootstrap
 * обновляется, а шлюз приложения сам переводит человека на безопасный next.
 */
export const useSignIn = () => {
  const client = useQueryClient();
  const refresh = useRefreshSession();
  const [pending, setPending] = useState(false);
  const [failure, setFailure] = useState<LoginFailure | null>(null);

  const submit = useCallback(
    async (email: string, password: string) => {
      setPending(true);
      setFailure(null);
      try {
        const res = await signInApi.login(email, password);
        // Остатки чужой сессии (истекла в этой вкладке) не должны достаться новому.
        await clearUserScopedCache(client);
        setCsrfToken(res.csrf_token);
        await refresh();
      } catch (error) {
        setFailure(toLoginFailure(error));
        // Устаревший CSRF лечится новым bootstrap: следующая попытка пройдёт.
        if (error instanceof ApiError && error.code === "csrf_failed") {
          await refresh();
        }
      } finally {
        setPending(false);
      }
    },
    [client, refresh],
  );

  return { submit, pending, failure };
};
