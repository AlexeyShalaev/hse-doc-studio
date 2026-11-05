import { useEffect, useRef } from "react";
import { type PendingSaveFlush, registerPendingSave } from "./pendingSaves";

/**
 * Keep `flush` registered while the component is mounted. The latest closure is
 * always the one that runs, so the callback can read props and state freely.
 */
export const usePendingSave = (
  flush: PendingSaveFlush,
  isDirty?: () => boolean,
): void => {
  const latest = useRef(flush);
  const latestDirty = useRef(isDirty);
  useEffect(() => {
    latest.current = flush;
    latestDirty.current = isDirty;
  });
  useEffect(
    () =>
      registerPendingSave(
        () => {
          return latest.current();
        },
        () => latestDirty.current?.() ?? false,
      ),
    [],
  );
};
