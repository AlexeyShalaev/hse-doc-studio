import { useEffect, useRef, useState } from "react";
import { createSSEStream } from "@shared/lib/sse";
import { imagesApi } from "@entities/compile-images";

export type InstallState = "idle" | "running" | "success" | "failure";

export type UseInstallImageStreamReturn = {
  state: InstallState;
  lines: string[];
  start: (image: string) => void;
  reset: () => void;
};

type DoneData = { status: "success" | "failure" };

export const useInstallImageStream = (): UseInstallImageStreamReturn => {
  const [state, setState] = useState<InstallState>("idle");
  const [lines, setLines] = useState<string[]>([]);
  const cleanupRef = useRef<(() => void) | null>(null);

  useEffect(
    () => () => {
      cleanupRef.current?.();
    },
    [],
  );

  const start = (image: string) => {
    cleanupRef.current?.();
    setLines([]);
    setState("running");

    const url = imagesApi.installStreamUrl(image);
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
        // server-side end. We only treat it as a failure if we haven't
        // already received a done event.
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
