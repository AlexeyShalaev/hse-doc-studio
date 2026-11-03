import { useQueryClient } from "@tanstack/react-query";
import { useCallback, useEffect, useRef, useState } from "react";
import { setCsrfToken } from "@shared/api";
import {
  PasskeyCeremonyError,
  cancelPasskeyCeremony,
  getPasskey,
  supportsAutofill,
  supportsPasskeys,
} from "@shared/lib/webauthn";
import { clearUserScopedCache, useRefreshSession } from "@entities/session";
import { signInApi, toLoginFailure } from "../api/signInApi";
import type { LoginFailure } from "../lib/loginErrors";

const toFailure = (error: unknown): LoginFailure | null => {
  if (error instanceof PasskeyCeremonyError) {
    // Человек закрыл окно выбора ключа: это не ошибка.
    return error.kind === "cancelled" ? null : { code: "passkey_failed" };
  }
  return toLoginFailure(error);
};

/**
 * Вход по passkey: кнопкой и автозаполнением поля логина (conditional UI). Ожидающая церемония
 * автозаполнения перезапускается после каждой попытки, пока экран входа открыт.
 */
export const usePasskeySignIn = (enabled: boolean) => {
  const client = useQueryClient();
  const refresh = useRefreshSession();
  const available = enabled && supportsPasskeys();
  const [pending, setPending] = useState(false);
  const [failure, setFailure] = useState<LoginFailure | null>(null);
  const [round, setRound] = useState(0);
  const started = useRef(false);

  const finish = useCallback(
    async (credential: Record<string, unknown>) => {
      setPending(true);
      const res = await signInApi.passkeyLogin(credential);
      await clearUserScopedCache(client);
      setCsrfToken(res.csrf_token);
      await refresh();
    },
    [client, refresh],
  );

  const ceremony = useCallback(
    async (autofill: boolean) => {
      const { options } = await signInApi.passkeyOptions();
      started.current = true;
      const credential = await getPasskey(options, { autofill });
      await finish(credential);
    },
    [finish],
  );

  useEffect(() => {
    if (!available) return;
    let alive = true;
    const isAlive = () => alive;
    void (async () => {
      if (!(await supportsAutofill()) || !isAlive()) return;
      try {
        await ceremony(true);
      } catch (error) {
        if (!isAlive()) return;
        const next = toFailure(error);
        // Отменённую автозаполнением церемонию прервала кнопка или уход со страницы.
        if (next) {
          setFailure(next);
          setPending(false);
          setRound((n) => n + 1);
        }
      }
    })();
    return () => {
      alive = false;
      if (started.current) void cancelPasskeyCeremony();
    };
  }, [available, ceremony, round]);

  const start = useCallback(async () => {
    setFailure(null);
    setPending(true);
    try {
      await ceremony(false);
    } catch (error) {
      setFailure(toFailure(error));
      setRound((n) => n + 1);
    } finally {
      setPending(false);
    }
  }, [ceremony]);

  return { available, start, pending, failure };
};
