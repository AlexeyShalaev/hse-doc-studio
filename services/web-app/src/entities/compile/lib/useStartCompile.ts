import { useCallback, useMemo } from "react";
import { useTranslation } from "react-i18next";
import { useDocuments, useTriggerCompile } from "@entities/document";
import { toast } from "@shared/lib";
import { useProjectBuildBlocks } from "./buildBlock";
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
 *
 * `block` — облачная сборка этого документа сейчас невозможна (нет раннера с
 * нужным тегом): кнопка гаснет и показывает пояснение, `start` ничего не делает.
 */
export const useStartCompile = (projectId: string, docId: string) => {
  const { mutateAsync: triggerCompile } = useTriggerCompile();
  const startStream = useCompileStreamStore((s) => s.start);
  const markPending = useCompileStreamStore((s) => s.markPending);
  const unmarkPending = useCompileStreamStore((s) => s.unmarkPending);
  const handleCompileError = useHandleCompileError();
  const slot = useCompileSlot(projectId, docId);
  const isProjectBuilding = useIsProjectBuilding(projectId);
  const { blockOf } = useProjectBuildBlocks(projectId);
  const block = blockOf(docId);

  const isRunning = isProjectBuilding;

  const start = useCallback(() => {
    if (isRunning || block !== null) return;
    markPending(projectId, docId);
    triggerCompile({ projectId, docId }).then(
      (result) => {
        startStream(projectId, docId, result.compile_id);
      },
      (err: unknown) => {
        unmarkPending(projectId, docId);
        handleCompileError(err);
      },
    );
  }, [
    isRunning,
    block,
    markPending,
    unmarkPending,
    triggerCompile,
    startStream,
    handleCompileError,
    projectId,
    docId,
  ]);

  return { start, isRunning, slot, block };
};

/**
 * "Собрать все документы" — fires a compile for every doc id, each wired to
 * the global SSE store. Marks all of them as pending synchronously so the
 * project-wide lock holds across the whole batch.
 *
 * Каждый запрос ждём своим промисом (`mutateAsync`): колбэки `mutate()`
 * React Query вызывает только у последнего вызова, и при пачке отказов
 * остальные документы навсегда оставались «в сборке».
 *
 * Документы без раннера пропускаются; `block` задан, когда собрать нельзя ни
 * один документ проекта.
 */
export const useStartCompileAll = (projectId: string) => {
  const { mutateAsync: triggerCompile } = useTriggerCompile();
  const startStream = useCompileStreamStore((s) => s.start);
  const markPending = useCompileStreamStore((s) => s.markPending);
  const unmarkPending = useCompileStreamStore((s) => s.unmarkPending);
  const handleCompileError = useHandleCompileError();
  const isProjectBuilding = useIsProjectBuilding(projectId);
  const { documents, blockOf } = useProjectBuildBlocks(projectId);
  const { t } = useTranslation("documents");

  const isRunning = isProjectBuilding;
  const block = useMemo(() => {
    if (!documents || documents.length === 0) return null;
    const blocks = documents.map((doc) => blockOf(doc.id));
    if (blocks.some((b) => b === null)) return null;
    return blocks[0] ?? null;
  }, [documents, blockOf]);

  const startAll = useCallback(
    (docIds: readonly string[]) => {
      if (isRunning || docIds.length === 0) return;
      const buildable = docIds.filter((docId) => blockOf(docId) === null);
      const skipped = docIds.length - buildable.length;
      if (skipped > 0) {
        toast.warning(
          t("compile.unavailable.buildAllPartial", { count: skipped }),
          {
            key: "compile-build-all-skipped",
            title: t("compile.unavailable.title"),
          },
        );
      }
      // Reserve the project-wide lock synchronously for ALL docs before any
      // POST goes out. This way the button is disabled the same tick the
      // click handler runs, regardless of how the network roundtrips race.
      for (const docId of buildable) markPending(projectId, docId);
      let errorShown = false;
      for (const docId of buildable) {
        triggerCompile({ projectId, docId }).then(
          (result) => {
            startStream(projectId, docId, result.compile_id);
          },
          (err: unknown) => {
            unmarkPending(projectId, docId);
            // For a batch trigger the same setup error fires once per
            // doc; show the toast just for the first.
            if (!errorShown) {
              errorShown = true;
              handleCompileError(err);
            }
          },
        );
      }
    },
    [
      isRunning,
      blockOf,
      markPending,
      unmarkPending,
      triggerCompile,
      startStream,
      handleCompileError,
      projectId,
      t,
    ],
  );

  return { startAll, isRunning, block };
};
