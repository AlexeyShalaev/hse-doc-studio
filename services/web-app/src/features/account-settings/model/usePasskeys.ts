import { useQueryClient } from "@tanstack/react-query";
import { useCallback, useRef, useState } from "react";
import { useTranslation } from "react-i18next";
import { ApiError, failureCode } from "@shared/api";
import { toast } from "@shared/lib";
import {
  PasskeyCeremonyError,
  createPasskey,
  getPasskey,
} from "@shared/lib/webauthn";
import { accountApi } from "../api/accountApi";
import { accountKeys } from "../api/accountQueries";
import { describeAgent } from "../lib/device";
import type { Failure } from "../lib/failure";

export type PasskeyBusy =
  | { kind: "add" }
  | { kind: "rename"; id: string }
  | { kind: "delete"; id: string }
  | null;

/** Код отказа для карточки; отмена окна выбора ключа ошибкой не считается. */
export const passkeyFailure = (error: unknown): Failure | null => {
  if (error instanceof PasskeyCeremonyError) {
    if (error.kind === "cancelled") return null;
    return {
      code:
        error.kind === "already_registered"
          ? "passkey_already_registered"
          : "passkey_failed",
    };
  }
  return { code: failureCode(error) };
};

const isReauthRequired = (error: unknown): boolean =>
  error instanceof ApiError && error.code === "reauth_required";

/** Имя нового ключа по устройству: «Chrome · macOS». Человек переименует его потом. */
export const deviceName = (): string =>
  describeAgent(typeof navigator === "undefined" ? "" : navigator.userAgent) ||
  "Passkey";

type Waiter = { resolve: () => void; reject: (error: unknown) => void };

/**
 * Действия с passkey в профиле. Добавить и удалить ключ можно только со свежей сессией: сервер
 * отвечает 403 reauth_required, тогда открывается подтверждение личности, и после него действие
 * повторяется само.
 */
export const usePasskeys = () => {
  const { t } = useTranslation("account");
  const client = useQueryClient();
  const [busy, setBusy] = useState<PasskeyBusy>(null);
  const [failure, setFailure] = useState<Failure | null>(null);
  const [reauthOpen, setReauthOpen] = useState(false);
  const [reauthPending, setReauthPending] = useState(false);
  const [reauthFailure, setReauthFailure] = useState<Failure | null>(null);
  const waiter = useRef<Waiter | null>(null);

  const refresh = useCallback(
    () => client.invalidateQueries({ queryKey: accountKeys.passkeys() }),
    [client],
  );

  const withReauth = useCallback(
    async <T>(action: () => Promise<T>): Promise<T> => {
      try {
        return await action();
      } catch (error) {
        if (!isReauthRequired(error)) throw error;
        setReauthFailure(null);
        await new Promise<void>((resolve, reject) => {
          waiter.current = { resolve, reject };
          setReauthOpen(true);
        });
        return action();
      }
    },
    [],
  );

  const run = useCallback(
    async (next: PasskeyBusy, job: () => Promise<void>) => {
      setFailure(null);
      setBusy(next);
      try {
        await job();
      } catch (error) {
        setFailure(passkeyFailure(error));
      } finally {
        setBusy(null);
      }
    },
    [],
  );

  const add = useCallback(
    () =>
      run({ kind: "add" }, async () => {
        const { options } = await withReauth(() => accountApi.passkeyOptions());
        const credential = await createPasskey(options);
        await accountApi.createPasskey({ name: deviceName(), credential });
        await refresh();
        toast.success(t("passkeys.toastAdded"));
      }),
    [refresh, run, t, withReauth],
  );

  const rename = useCallback(
    (id: string, name: string) =>
      run({ kind: "rename", id }, async () => {
        await accountApi.renamePasskey(id, name);
        await refresh();
      }),
    [refresh, run],
  );

  const remove = useCallback(
    (id: string) =>
      run({ kind: "delete", id }, async () => {
        await withReauth(() => accountApi.deletePasskey(id));
        await refresh();
        toast.success(t("passkeys.toastRemoved"));
      }),
    [refresh, run, t, withReauth],
  );

  const settle = (error?: unknown) => {
    const current = waiter.current;
    waiter.current = null;
    setReauthOpen(false);
    setReauthPending(false);
    if (!current) return;
    if (error === undefined) current.resolve();
    else current.reject(error);
  };

  const confirm = async (body: () => Promise<unknown>) => {
    setReauthPending(true);
    setReauthFailure(null);
    try {
      await body();
      settle();
    } catch (error) {
      setReauthPending(false);
      setReauthFailure(passkeyFailure(error));
    }
  };

  const reauth = {
    open: reauthOpen,
    pending: reauthPending,
    failure: reauthFailure,
    withPassword: (password: string) =>
      confirm(() => accountApi.reauth({ password, credential: null })),
    withPasskey: () =>
      confirm(async () => {
        const { options } = await accountApi.reauthOptions();
        const credential = await getPasskey(options);
        await accountApi.reauth({ password: null, credential });
      }),
    cancel: () => {
      settle(new PasskeyCeremonyError("cancelled"));
    },
  };

  return { busy, failure, add, rename, remove, reauth };
};
