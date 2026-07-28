import { useEffect, useRef, useState } from "react";
import { createSSEStream } from "@shared/lib/sse";

export type InstallState = "idle" | "running" | "success" | "failure";

export type UseSseInstallReturn = {
  state: InstallState;
  lines: string[];
  start: (url: string) => void;
  reset: () => void;
};

type DoneData = { status: "success" | "failure" };

/**
 * Generic consumer for the backend's `event: log` / `event: done` install
 * streams (engine pull, model pull). The caller supplies the full SSE URL.
 * Mirrors the compile/LanguageTool install stream hook.
 */
export const useSseInstall = (): UseSseInstallReturn => {
  const [state, setState] = useState<InstallState>("idle");
  const [lines, setLines] = useState<string[]>([]);
  const cleanupRef = useRef<(() => void) | null>(null);

  useEffect(
    () => () => {
      cleanupRef.current?.();
    },
    [],
  );

  const start = (url: string) => {
    cleanupRef.current?.();
    setLines([]);
    setState("running");

    cleanupRef.current = createSSEStream<string | DoneData>(
      url,
      (event) => {
        if (event.type === "log" && typeof event.data === "string") {
          setLines((prev) => [...prev, event.data as string]);
          return;
        }
        if (event.type === "done" && typeof event.data === "object") {
          setState(event.data.status === "success" ? "success" : "failure");
          cleanupRef.current?.();
          cleanupRef.current = null;
        }
      },
      () => {
        // onerror fires on both transient reconnects and server-side end; only
        // treat it as failure if we haven't already seen a done event.
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
