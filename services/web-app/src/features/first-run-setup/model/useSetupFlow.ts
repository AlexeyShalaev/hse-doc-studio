import { useCallback, useEffect, useRef, useState } from "react";
import { setupApi, type ProbeFolderResult } from "@entities/setup";

export type SetupFlowStatus =
  | "idle"
  | "probing"
  | "probed"
  | "applying"
  | "restarting"
  | "done"
  | "failed";

const POLL_INTERVAL_MS = 2_000;
const POLL_TIMEOUT_MS = 3 * 60 * 1_000;
const RELOAD_DELAY_MS = 1_000;

const delay = (ms: number): Promise<void> =>
  new Promise((resolve) => {
    setTimeout(resolve, ms);
  });

export type UseSetupFlowResult = {
  status: SetupFlowStatus;
  probe: ProbeFolderResult | null;
  /** Машиночитаемый код отказа — текст подбирает экран по своим словарям. */
  errorCode: string | null;
  isBusy: boolean;
  checkFolder: (hostPath: string) => void;
  apply: (
    hostPath: string,
    fontsHostPath?: string | null,
    prefetchTexImage?: boolean,
  ) => void;
  reset: () => void;
};

/**
 * Ведёт мастер первоначальной настройки: проверить папку → применить.
 *
 * Применение убивает собственный бэкенд: примонтировать каталог к живому
 * контейнеру докер не умеет, поэтому приложение пересоздаёт себя. Значит после
 * запроса сервер на десятки секунд перестаёт отвечать, и ошибки соединения в
 * этот момент — нормальный ход событий, а не сбой. Опрашиваем состояние
 * установки, пока оно не станет готовым, и только тогда перезагружаем страницу.
 *
 * Тот же приём, что у обновления одной кнопкой (useSelfUpdate) — и по той же
 * причине: TanStack Query здесь не помощник, ему нечего кэшировать, пока
 * сервера нет.
 */
export const useSetupFlow = (): UseSetupFlowResult => {
  const [status, setStatus] = useState<SetupFlowStatus>("idle");
  const [probe, setProbe] = useState<ProbeFolderResult | null>(null);
  const [errorCode, setErrorCode] = useState<string | null>(null);
  const aliveRef = useRef(false);

  useEffect(() => {
    aliveRef.current = true;
    return () => {
      aliveRef.current = false;
    };
  }, []);

  // Через функцию, а не чтением ref внутри цикла: так условие остаётся
  // настоящим boolean и не схлопывается анализом потока в константу.
  const isAlive = useCallback((): boolean => aliveRef.current, []);

  const reset = useCallback(() => {
    setStatus("idle");
    setProbe(null);
    setErrorCode(null);
  }, []);

  const checkFolder = useCallback(
    (hostPath: string) => {
      setErrorCode(null);
      setProbe(null);
      setStatus("probing");
      void (async () => {
        try {
          const result = await setupApi.probeFolder(hostPath);
          if (!isAlive()) return;
          setProbe(result);
          setStatus("probed");
        } catch {
          if (!isAlive()) return;
          setErrorCode("request_failed");
          setStatus("failed");
        }
      })();
    },
    [isAlive],
  );

  const apply = useCallback(
    (
      hostPath: string,
      fontsHostPath?: string | null,
      prefetchTexImage = true,
    ) => {
      setErrorCode(null);
      setStatus("applying");

      void (async () => {
        try {
          const result = await setupApi.apply(
            hostPath,
            fontsHostPath,
            prefetchTexImage,
          );
          if (!isAlive()) return;
          if (result.probe) setProbe(result.probe);
          if (!result.applied) {
            setErrorCode(result.error_code ?? "recreate_failed");
            setStatus("failed");
            return;
          }
        } catch {
          if (!isAlive()) return;
          setErrorCode("request_failed");
          setStatus("failed");
          return;
        }

        setStatus("restarting");
        const deadline = Date.now() + POLL_TIMEOUT_MS;
        // Прежний сервер ещё жив пару секунд и ответил бы «не настроено» —
        // ждём, прежде чем поверить первому же ответу.
        await delay(POLL_INTERVAL_MS);

        while (isAlive() && Date.now() < deadline) {
          try {
            const state = await setupApi.status();
            if (state.is_ready) {
              setStatus("done");
              await delay(RELOAD_DELAY_MS);
              window.location.reload();
              return;
            }
          } catch {
            // Контейнер пересоздаётся — соединения сейчас и не должно быть.
          }
          await delay(POLL_INTERVAL_MS);
        }

        if (isAlive()) {
          setErrorCode("restart_timeout");
          setStatus("failed");
        }
      })();
    },
    [isAlive],
  );

  return {
    status,
    probe,
    errorCode,
    isBusy:
      status === "probing" || status === "applying" || status === "restarting",
    checkFolder,
    apply,
    reset,
  };
};
