import { useCallback } from "react";
import { useDocuments, useTriggerCompile } from "@entities/document";
import { useCompileSlot, useCompileStreamStore } from "./compileStreamStore";
import { useHandleCompileError } from "./handleCompileError";

/**
 * True if ANY compile is in flight or streaming for the given project. Used
 * so every Собрать/Пересобрать button shares one disabled state — clicking
 * "Собрать все" must block individual rebuilds, and vice versa.
 *
 * Three sources of truth, OR-ed:
 *  - `pending[key]` — POST has been fired, response not yet processed.
 *  - `streams[key].status === "running"` — SSE is active in this tab.
 *  - `doc.status === "building"` in the cached documents list — covers page
 *    reload / new browser tab / another tab triggered the build. This stays
 *    true until the backend marks the doc finished, even if our in-memory
 *    store is empty (e.g. right after reload, before SSE re-attaches).
 *
 * Relying on React-Query's `isPending` alone is not enough: with several
 * parallel `mutate()` calls it only tracks the most recent one, so the lock
 * would release as soon as the fastest POST finished.
 */
export const useIsProjectBuilding = (projectId: string): boolean => {
  const storeFlag = useCompileStreamStore((s) => {
    const prefix = `${projectId}::`;
    for (const k of Object.keys(s.pending)) {
      if (k.startsWith(prefix)) return true;
    }
    for (const [k, slot] of Object.entries(s.streams)) {
      if (k.startsWith(prefix) && slot.status === "running") return true;
    }
    return false;
  });
  const { data: documents } = useDocuments(projectId);
  const backendFlag = documents
    ? documents.some((d) => d.status === "building")
    : false;
  return storeFlag || backendFlag;
};

/**
 * Centralised "start a build" action used by every place that has a
 * Собрать/Пересобрать button. Wires the POST and the SSE subscription, and
 * keeps a project-wide lock so other compile buttons stay disabled for the
 * full duration of the build.
 */
export const useStartCompile = (projectId: string, docId: string) => {
  const { mutate: triggerCompile } = useTriggerCompile();
  const startStream = useCompileStreamStore((s) => s.start);
  const markPending = useCompileStreamStore((s) => s.markPending);
  const unmarkPending = useCompileStreamStore((s) => s.unmarkPending);
  const handleCompileError = useHandleCompileError();
  const slot = useCompileSlot(projectId, docId);
  const isProjectBuilding = useIsProjectBuilding(projectId);

  const isRunning = isProjectBuilding;

  const start = useCallback(() => {
    if (isRunning) return;
    markPending(projectId, docId);
    triggerCompile(
      { projectId, docId },
      {
        onSuccess: (result) => {
          startStream(projectId, docId, result.compile_id);
        },
        onError: (err) => {
          unmarkPending(projectId, docId);
          handleCompileError(err);
        },
      },
    );
  }, [
    isRunning,
    markPending,
    unmarkPending,
    triggerCompile,
    startStream,
    handleCompileError,
    projectId,
    docId,
  ]);

  return { start, isRunning, slot };
};

/**
 * "Собрать все документы" — fires a compile for every doc id, each wired to
 * the global SSE store. Marks all of them as pending synchronously so the
 * project-wide lock holds across the whole batch.
 */
export const useStartCompileAll = (projectId: string) => {
  const { mutate: triggerCompile } = useTriggerCompile();
  const startStream = useCompileStreamStore((s) => s.start);
  const markPending = useCompileStreamStore((s) => s.markPending);
  const unmarkPending = useCompileStreamStore((s) => s.unmarkPending);
  const handleCompileError = useHandleCompileError();
  const isProjectBuilding = useIsProjectBuilding(projectId);

  const isRunning = isProjectBuilding;

  const startAll = useCallback(
    (docIds: readonly string[]) => {
      if (isRunning || docIds.length === 0) return;
      // Reserve the project-wide lock synchronously for ALL docs before any
      // POST goes out. This way the button is disabled the same tick the
      // click handler runs, regardless of how the network roundtrips race.
      for (const docId of docIds) markPending(projectId, docId);
      let errorShown = false;
      for (const docId of docIds) {
        triggerCompile(
          { projectId, docId },
          {
            onSuccess: (result) => {
              startStream(projectId, docId, result.compile_id);
            },
            onError: (err) => {
              unmarkPending(projectId, docId);
              // For a batch trigger the same setup error fires once per
              // doc; show the toast just for the first.
              if (!errorShown) {
                errorShown = true;
                handleCompileError(err);
              }
            },
          },
        );
      }
    },
    [
      isRunning,
      markPending,
      unmarkPending,
      triggerCompile,
      startStream,
      handleCompileError,
      projectId,
    ],
  );

  return { startAll, isRunning };
};
