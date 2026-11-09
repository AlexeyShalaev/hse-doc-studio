import { useState } from "react";
import { ApiError, failureCode } from "@shared/api";
import {
  useApproveSigningTask,
  useReturnSigningTask,
  useSignSigningTask,
  useSigningTask,
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

/** Коды отказов действий, у которых на странице свой текст; остальное `unknown`. */
const KNOWN_FAILURES = new Set([
  "doc_changed",
  "not_your_turn",
  "image_required",
  "plate_required",
  "network",
]);

const failureOf = (error: unknown): string => {
  const code = failureCode(error);
  return KNOWN_FAILURES.has(code) ? code : "unknown";
};

/**
 * Данные и действия страницы подписанта. Ответ действия сразу ложится в кэш задачи
 * (хуки сущности), отказ перечитывает её: после 409 страница уже показывает новую версию.
 */
export const useSigningPage = (projectId: string, routeId: string) => {
  const task = useSigningTask(projectId, routeId);
  const approveTask = useApproveSigningTask(projectId, routeId);
  const signTask = useSignSigningTask(projectId, routeId);
  const returnTask = useReturnSigningTask(projectId, routeId);
  const [failure, setFailure] = useState<string | null>(null);

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

  const approve = (options: ApproveOptions = {}) => {
    setFailure(null);
    approveTask.mutate(
      {
        expected,
        method: options.method ?? null,
        sign: options.sign ?? null,
      },
      {
        onError: (error) => {
          setFailure(failureOf(error));
        },
      },
    );
  };

  const sign = (key: SigningKeyRequest) => {
    setFailure(null);
    signTask.mutate(
      { expected, identity_id: key.identity_id, passphrase: key.passphrase },
      {
        onError: (error) => {
          setFailure(failureOf(error));
        },
      },
    );
  };

  /** Вернуть на доработку; true, если сервер принял (окно закрывается). */
  const returnForRework = async (comment: string): Promise<boolean> => {
    setFailure(null);
    try {
      await returnTask.mutateAsync(comment.trim());
      return true;
    } catch (error) {
      setFailure(failureOf(error));
      return false;
    }
  };

  const slot = (ready: SigningTask): SigningSlotContext => ({
    projectId,
    routeId,
    task: ready,
    busy,
    expected,
    approve,
    sign,
  });

  return {
    state,
    busy,
    approving: approveTask.isPending,
    failure,
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
