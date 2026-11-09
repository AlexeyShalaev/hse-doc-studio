import { useState } from "react";
import { ApiError } from "@shared/api";
import {
  signingFailureOf,
  useApproveSigningTask,
  useReturnSigningTask,
  useSignSigningTask,
  useSigningTask,
  type SigningFailure,
  type SigningKeyRequest,
  type SigningTask,
} from "@entities/signing-route";
import { expectedTokens } from "../lib/signingState";
import type { ApproveOptions, SigningSlotContext } from "./extension";

export type SigningPageState =
  | { kind: "loading" }
  /** Нет маршрута или проекта, не участник, локальный режим: сервер отвечает 404. */
  | { kind: "not_found" }
  | { kind: "error" }
  | { kind: "ready"; task: SigningTask };

/**
 * Данные и действия страницы подписанта. Ответ действия сразу ложится в кэш задачи
 * (хуки сущности), отказ перечитывает её: после 409 страница уже показывает новую версию.
 */
export const useSigningPage = (projectId: string, routeId: string) => {
  const task = useSigningTask(projectId, routeId);
  const approveTask = useApproveSigningTask(projectId, routeId);
  const signTask = useSignSigningTask(projectId, routeId);
  const returnTask = useReturnSigningTask(projectId, routeId);
  const [failure, setFailure] = useState<SigningFailure | null>(null);

  // Фоновое перечитывание с ошибкой не прячет уже показанную задачу.
  const state: SigningPageState = task.data
    ? { kind: "ready", task: task.data }
    : task.isError
      ? task.error instanceof ApiError && task.error.status === 404
        ? { kind: "not_found" }
        : { kind: "error" }
      : { kind: "loading" };

  const busy =
    approveTask.isPending || signTask.isPending || returnTask.isPending;
  const expected = task.data ? expectedTokens(task.data) : {};

  const approve = async (
    options: ApproveOptions = {},
  ): Promise<SigningTask | null> => {
    setFailure(null);
    try {
      return await approveTask.mutateAsync({
        expected: options.expected ?? expected,
        method: options.method ?? null,
        sign: options.sign ?? null,
      });
    } catch (error) {
      setFailure(signingFailureOf(error));
      return null;
    }
  };

  const sign = async (
    key: SigningKeyRequest,
    fresh?: Record<string, string>,
  ): Promise<SigningTask | null> => {
    setFailure(null);
    try {
      return await signTask.mutateAsync({
        expected: fresh ?? expected,
        identity_id: key.identity_id,
        passphrase: key.passphrase,
      });
    } catch (error) {
      setFailure(signingFailureOf(error));
      return null;
    }
  };

  /** Вернуть на доработку; true, если сервер принял (окно закрывается). */
  const returnForRework = async (comment: string): Promise<boolean> => {
    setFailure(null);
    try {
      await returnTask.mutateAsync(comment.trim());
      return true;
    } catch (error) {
      setFailure(signingFailureOf(error));
      return false;
    }
  };

  const slot = (ready: SigningTask): SigningSlotContext => ({
    projectId,
    routeId,
    task: ready,
    busy,
    failure: failure?.code ?? null,
    expected,
    approve,
    sign,
  });

  return {
    state,
    busy,
    approving: approveTask.isPending,
    failure: failure?.code ?? null,
    failureDetail: failure?.detail ?? null,
    dismissFailure: () => {
      setFailure(null);
    },
    approve,
    returnForRework,
    slot,
    retry: () => {
      void task.refetch();
    },
  };
};
