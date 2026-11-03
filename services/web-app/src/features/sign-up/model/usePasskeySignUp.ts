import { useQueryClient } from "@tanstack/react-query";
import { useCallback, useState } from "react";
import { useNavigate } from "react-router";
import { failureCode, setCsrfToken } from "@shared/api";
import { describeAgent } from "@shared/lib/device";
import {
  PasskeyCeremonyError,
  createPasskey,
  supportsPasskeys,
} from "@shared/lib/webauthn";
import {
  DEFAULT_NEXT_PATH,
  clearUserScopedCache,
  useRefreshSession,
} from "@entities/session";
import { signUpApi } from "../api/signUpApi";
import { PASSKEY_CEREMONY_FAILED } from "../lib/registerErrors";
import type { SignUpFailure } from "./useSignUp";

const toFailure = (error: unknown): SignUpFailure | null => {
  if (error instanceof PasskeyCeremonyError) {
    // Человек закрыл окно создания ключа: это не ошибка.
    return error.kind === "cancelled"
      ? null
      : { code: PASSKEY_CEREMONY_FAILED };
  }
  return { code: failureCode(error) };
};

/**
 * Регистрация по приглашению сразу с passkey, без пароля. Доступна, если на установке включён passkey,
 * браузер его умеет и приглашение выписано на конкретный адрес (почта подтверждена самим приглашением).
 * Успех открывает сессию так же, как вход; страница приглашения шлюзом не закрыта, поэтому уходим на главную сами.
 */
export const usePasskeySignUp = (
  invitationToken: string,
  { enabled }: { enabled: boolean },
) => {
  const client = useQueryClient();
  const refresh = useRefreshSession();
  const navigate = useNavigate();
  const available = enabled && supportsPasskeys();
  const [pending, setPending] = useState(false);
  const [failure, setFailure] = useState<SignUpFailure | null>(null);

  const start = useCallback(
    async (name: string) => {
      setFailure(null);
      setPending(true);
      try {
        const { options } = await signUpApi.passkeyOptions({
          invitation_token: invitationToken,
          name,
        });
        const credential = await createPasskey(options);
        const agent =
          typeof navigator === "undefined" ? "" : navigator.userAgent;
        const res = await signUpApi.passkeyRegister({
          invitation_token: invitationToken,
          name,
          passkey_name: describeAgent(agent) || null,
          credential,
        });
        await clearUserScopedCache(client);
        setCsrfToken(res.csrf_token);
        await refresh();
        void navigate(DEFAULT_NEXT_PATH, { replace: true });
      } catch (error) {
        const next = toFailure(error);
        setFailure(next);
        if (next?.code === "csrf_failed") await refresh();
      } finally {
        setPending(false);
      }
    },
    [client, invitationToken, navigate, refresh],
  );

  return { available, start, pending, failure };
};
