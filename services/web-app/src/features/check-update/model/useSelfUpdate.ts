import { useCallback, useEffect, useRef, useState } from "react";
import { useTranslation } from "react-i18next";
import { systemApi } from "@entities/system";

export type SelfUpdateStatus =
  | "idle"
  | "starting"
  | "updating"
  | "done"
  | "failed";

const POLL_INTERVAL_MS = 3_000;
const POLL_TIMEOUT_MS = 5 * 60 * 1_000;
const RELOAD_DELAY_MS = 1_500;

const delay = (ms: number): Promise<void> =>
  new Promise((resolve) => {
    setTimeout(resolve, ms);
  });

export type UseSelfUpdateResult = {
  status: SelfUpdateStatus;
  error: string | null;
  isBusy: boolean;
  start: (version: string) => void;
};

// Drives the one-click self-update: POST /system/self-update spawns a detached
// updater container that recreates the backend, so the backend goes offline
// mid-update. We can't rely on TanStack Query's cached useSystemInfo here — we
// poll the endpoint raw, tolerating the connection errors that are expected
// while the container is being recreated, until the reported version flips to
// the target (success) or we time out (the updater auto-rolls-back on its
// side, so a timeout means "still on the old version — check the updater log").
export const useSelfUpdate = (): UseSelfUpdateResult => {
  const { t } = useTranslation("checkUpdate");
  const [status, setStatus] = useState<SelfUpdateStatus>("idle");
  const [error, setError] = useState<string | null>(null);
  const aliveRef = useRef(false);

  useEffect(() => {
    aliveRef.current = true;
    return () => {
      aliveRef.current = false;
    };
  }, []);

  // Read through a function so the async loop bails out if the modal closes
  // mid-update. Going via a call (vs reading aliveRef.current inline) also keeps
  // it a genuine boolean condition — a direct read gets flow-narrowed to a
  // constant by no-unnecessary-condition since every write it sees is literal.
  const isAlive = useCallback((): boolean => aliveRef.current, []);

  const start = useCallback(
    (version: string) => {
      setError(null);
      setStatus("starting");

      void (async () => {
        try {
          await systemApi.selfUpdate(version);
        } catch {
          if (isAlive()) {
            setError(t("selfUpdate.startFailed"));
            setStatus("failed");
          }
          return;
        }

        if (!isAlive()) return;
        setStatus("updating");

        const deadline = Date.now() + POLL_TIMEOUT_MS;
        // The old backend is still up for a moment; the target version won't
        // match it, so the success check below naturally waits for the new one.
        await delay(POLL_INTERVAL_MS);

        while (isAlive() && Date.now() < deadline) {
          try {
            const info = await systemApi.getSystemInfo();
            if (info.version === version) {
              if (isAlive()) {
                setStatus("done");
                await delay(RELOAD_DELAY_MS);
                window.location.reload();
              }
              return;
            }
          } catch {
            // Backend is offline while its container is recreated — expected.
          }
          await delay(POLL_INTERVAL_MS);
        }

        if (isAlive()) {
          setError(t("selfUpdate.timeout"));
          setStatus("failed");
        }
      })();
    },
    [isAlive, t],
  );

  return {
    status,
    error,
    isBusy: status === "starting" || status === "updating",
    start,
  };
};
