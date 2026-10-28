import { useCallback, useState } from "react";
import { failureCode } from "@shared/api";
import type { RecoveryFailure } from "../lib/recoveryErrors";

/**
 * Один запрос с исходом «получилось с данными» или «отказ с кодом».
 * Используется формами «забыл пароль», «новый пароль» и повторной отправкой.
 */
export const useRecoveryRequest = <Input, Output>(
  call: (input: Input) => Promise<Output>,
  onFailure?: (code: string) => void | Promise<void>,
) => {
  const [pending, setPending] = useState(false);
  const [failure, setFailure] = useState<RecoveryFailure | null>(null);
  const [result, setResult] = useState<Output | null>(null);

  const submit = useCallback(
    async (input: Input) => {
      setPending(true);
      setFailure(null);
      try {
        setResult(await call(input));
      } catch (error) {
        const code = failureCode(error);
        setFailure({ code });
        await onFailure?.(code);
      } finally {
        setPending(false);
      }
    },
    [call, onFailure],
  );

  return { submit, pending, failure, result };
};
