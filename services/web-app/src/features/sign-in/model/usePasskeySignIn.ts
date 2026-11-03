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

const MAX_AUTOFILL_RESTARTS = 3;

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
  const restarts = useRef(0);
  // После неудачи автозаполнение запускается заново, но не бесконечно: иначе сломанный ответ сервера
  // превращался бы в поток запросов вызова.
  const restart = useCallback(() => {
    if (restarts.current < MAX_AUTOFILL_RESTARTS) {
      restarts.current += 1;
      setRound((n) => n + 1);
    }
  }, []);

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

  const ceremony = useCallback(async () => {
    const { options } = await signInApi.passkeyOptions();
    started.current = true;
    await finish(await getPasskey(options));
  }, [finish]);

  useEffect(() => {
    if (!available) return;
    let alive = true;
    const isAlive = () => alive;
    void (async () => {
      if (!(await supportsAutofill()) || !isAlive()) return;
      let options: Record<string, unknown>;
      try {
        ({ options } = await signInApi.passkeyOptions());
      } catch {
        // Вызов не выдан (лимит, passkey выключен): автозаполнение просто не включается, кнопка остаётся.
        return;
      }
      if (!isAlive()) return;
      started.current = true;
      try {
        await finish(await getPasskey(options, { autofill: true }));
      } catch (error) {
        if (!isAlive()) return;
        const next = toFailure(error);
        // Отменённую автозаполнением церемонию прервала кнопка или уход со страницы.
        if (next) {
          setFailure(next);
          setPending(false);
          restart();
        }
      }
    })();
    return () => {
      alive = false;
      if (started.current) void cancelPasskeyCeremony();
    };
  }, [available, finish, restart, round]);

  const start = useCallback(async () => {
    setFailure(null);
    setPending(true);
    try {
      await ceremony();
    } catch (error) {
      setFailure(toFailure(error));
      restart();
    } finally {
      setPending(false);
    }
  }, [ceremony, restart]);

  return { available, start, pending, failure };
};
