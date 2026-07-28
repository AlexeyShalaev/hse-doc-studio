import { useEffect, useRef, useState } from "react";
import { createSSEStream } from "@shared/lib/sse";
import {
  officeServicesApi,
  type OfficeServiceId,
} from "@entities/office-services";

export type InstallState = "idle" | "running" | "success" | "failure";

export type UseOfficeInstallStreamReturn = {
  state: InstallState;
  lines: string[];
  start: (service: OfficeServiceId, image: string) => void;
  reset: () => void;
};

type DoneData = { status: "success" | "failure" };

export const useOfficeInstallStream = (): UseOfficeInstallStreamReturn => {
  const [state, setState] = useState<InstallState>("idle");
  const [lines, setLines] = useState<string[]>([]);
  const cleanupRef = useRef<(() => void) | null>(null);

  useEffect(
    () => () => {
      cleanupRef.current?.();
    },
    [],
  );

  const start = (service: OfficeServiceId, image: string) => {
    cleanupRef.current?.();
    setLines([]);
    setState("running");

    const url = officeServicesApi.installStreamUrl(service, image);
    cleanupRef.current = createSSEStream<string | DoneData>(
      url,
      (event) => {
        if (event.type === "log" && typeof event.data === "string") {
          setLines((prev) => [...prev, event.data as string]);
          return;
        }
        if (event.type === "done" && typeof event.data === "object") {
          const done = event.data;
          setState(done.status === "success" ? "success" : "failure");
          cleanupRef.current?.();
          cleanupRef.current = null;
        }
      },
      () => {
        // EventSource fires onerror both on transient reconnect and on
        // server-side end. Only treat it as a failure while still running.
        setState((s) => (s === "running" ? "failure" : s));
      },
    );
  };

  const reset = () => {
    cleanupRef.current?.();
    cleanupRef.current = null;
    setLines([]);
    setState("idle");
  };

  return { state, lines, start, reset };
};
