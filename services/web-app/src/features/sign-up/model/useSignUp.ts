import { useCallback, useState } from "react";
import { failureCode } from "@shared/api";
import { useRefreshSession, type RegisterResponse } from "@entities/session";
import { signUpApi } from "../api/signUpApi";

export type SignUpResult = RegisterResponse & { email: string };
export type SignUpFailure = { code: string };

/** Регистрация: либо итог (проверьте почту, ждёт одобрения), либо отказ. */
export const useSignUp = (invitationToken: string | null) => {
  const refresh = useRefreshSession();
  const [pending, setPending] = useState(false);
  const [failure, setFailure] = useState<SignUpFailure | null>(null);
  const [result, setResult] = useState<SignUpResult | null>(null);

  const submit = useCallback(
    async (input: { name: string; email: string; password: string }) => {
      setPending(true);
      setFailure(null);
      try {
        const res = await signUpApi.register({
          ...input,
          invitation_token: invitationToken,
        });
        setResult({ ...res, email: input.email });
      } catch (error) {
        const code = failureCode(error);
        setFailure({ code });
        // Устаревший CSRF лечится новым bootstrap: следующая попытка пройдёт.
        if (code === "csrf_failed") {
          await refresh();
        }
      } finally {
        setPending(false);
      }
    },
    [invitationToken, refresh],
  );

  return { submit, pending, failure, result };
};
