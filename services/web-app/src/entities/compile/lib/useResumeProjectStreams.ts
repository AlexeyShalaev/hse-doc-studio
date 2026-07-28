import { useEffect, useRef } from "react";
import { useQueryClient } from "@tanstack/react-query";
import { documentKeys, useDocuments } from "@entities/document";
import { useCompileStreamStore } from "./compileStreamStore";

/**
 * Keeps the in-memory compile stream store in sync with the backend state
 * for `projectId`. Specifically:
 *
 *   1. On mount and on every refresh of `useDocuments`, looks for any doc
 *      with `status === "building"` and a known `last_compile_id`. For each,
 *      opens an SSE subscription (idempotent if the slot is already correct).
 *      This re-attaches live tailing after a page reload or a fresh tab.
 *
 *   2. Subscribes to the store and, whenever a previously-running slot for
 *      this project transitions out of "running" (build finished), invalidates
 *      the documents query so the dot/status refreshes from "building" to
 *      "ok"/"warn"/"err".
 *
 * Called once per workspace mount.
 */
export const useResumeProjectStreams = (projectId: string): void => {
  const { data: documents } = useDocuments(projectId);
  const start = useCompileStreamStore((s) => s.start);
  const queryClient = useQueryClient();

  // Re-attach SSE for any doc the backend says is currently building.
  useEffect(() => {
    if (!documents) return;
    const snapshot = useCompileStreamStore.getState().streams;
    for (const doc of documents) {
      if (doc.status !== "building" || !doc.last_compile_id) continue;
      const k = `${projectId}::${doc.id}`;
      const existing = snapshot[k];
      if (existing?.compileId === doc.last_compile_id) continue;
      start(projectId, doc.id, doc.last_compile_id);
    }
  }, [documents, projectId, start]);

  // Invalidate the documents query when a build wraps up so the UI reflects
  // the final status (ok/warn/err) instead of remaining stuck on "building".
  const prevRunningRef = useRef<Set<string>>(new Set());
  useEffect(() => {
    const unsubscribe = useCompileStreamStore.subscribe((state) => {
      const prefix = `${projectId}::`;
      const currentlyRunning = new Set<string>();
      for (const [k, slot] of Object.entries(state.streams)) {
        if (k.startsWith(prefix) && slot.status === "running") {
          currentlyRunning.add(k);
        }
      }
      // Find slots that were running last tick but are no longer.
      let anyFinished = false;
      for (const k of prevRunningRef.current) {
        if (!currentlyRunning.has(k)) {
          anyFinished = true;
          break;
        }
      }
      prevRunningRef.current = currentlyRunning;
      if (anyFinished) {
        void queryClient.invalidateQueries({
          queryKey: documentKeys.lists(projectId),
        });
      }
    });
    return unsubscribe;
  }, [projectId, queryClient]);
};
