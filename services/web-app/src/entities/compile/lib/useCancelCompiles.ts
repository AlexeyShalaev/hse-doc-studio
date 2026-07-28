import { useCallback } from "react";
import { useCancelCompile } from "@entities/document";
import { useCompileStreamStore } from "./compileStreamStore";

/** True if any running slot in this project is currently flagged stalled. */
export const useIsProjectStalled = (projectId: string): boolean =>
  useCompileStreamStore((s) => {
    const prefix = `${projectId}::`;
    for (const [k, slot] of Object.entries(s.streams)) {
      if (k.startsWith(prefix) && slot.status === "running" && slot.isStalled) {
        return true;
      }
    }
    return false;
  });

/**
 * "Cancel everything that's currently building in this project." Used by the
 * project-wide build-all UI and any escape hatch we expose when a build is
 * detected as stalled. For every in-memory slot in `running` state we fire
 * POST /cancel, then optimistically mark the slot as cancelled so the UI
 * lock releases without waiting for the next documents refetch.
 *
 * If the slot has no compile_id (e.g. POST in flight, never got SSE), we
 * just clear the local pending mark — there's nothing to cancel server-side.
 */
export const useCancelProjectCompiles = (projectId: string) => {
  const { mutate: cancelCompile } = useCancelCompile();
  const streams = useCompileStreamStore((s) => s.streams);
  const pending = useCompileStreamStore((s) => s.pending);
  const markCancelled = useCompileStreamStore((s) => s.markCancelled);
  const unmarkPending = useCompileStreamStore((s) => s.unmarkPending);

  const cancelAll = useCallback(() => {
    const prefix = `${projectId}::`;
    for (const [k, slot] of Object.entries(streams)) {
      if (!k.startsWith(prefix)) continue;
      if (slot.status !== "running") continue;
      const docId = k.slice(prefix.length);
      cancelCompile(
        { projectId, compileId: slot.compileId },
        {
          onSettled: () => {
            markCancelled(projectId, docId);
          },
        },
      );
    }
    for (const k of Object.keys(pending)) {
      if (!k.startsWith(prefix)) continue;
      const docId = k.slice(prefix.length);
      unmarkPending(projectId, docId);
    }
  }, [
    streams,
    pending,
    projectId,
    cancelCompile,
    markCancelled,
    unmarkPending,
  ]);

  return { cancelAll };
};

/** Cancel a single doc's in-flight build, if any. */
export const useCancelDocCompile = (projectId: string, docId: string) => {
  const { mutate: cancelCompile, isPending } = useCancelCompile();
  const slot = useCompileStreamStore(
    (s) => s.streams[`${projectId}::${docId}`],
  );
  const markCancelled = useCompileStreamStore((s) => s.markCancelled);
  const unmarkPending = useCompileStreamStore((s) => s.unmarkPending);

  const cancel = useCallback(() => {
    if (slot?.status !== "running") {
      unmarkPending(projectId, docId);
      return;
    }
    cancelCompile(
      { projectId, compileId: slot.compileId },
      {
        onSettled: () => {
          markCancelled(projectId, docId);
        },
      },
    );
  }, [slot, projectId, docId, cancelCompile, markCancelled, unmarkPending]);

  return { cancel, isCancelling: isPending };
};
