import { useCallback, useMemo } from "react";
import { useTranslation } from "react-i18next";
import { useQueryClient } from "@tanstack/react-query";
import {
  getDocMeta,
  useDocuments,
  useTriggerCompile,
} from "@entities/document";
import { runnerKeys } from "@entities/runner";
import { useRouteEditGuard } from "@entities/signing-route";
import { toast } from "@shared/lib";
import {
  blockOfRefusal,
  kindsText,
  useProjectBuildBlocks,
  type BuildBlock,
} from "./buildBlock";
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
  const routeGuard = useRouteEditGuard(projectId);

  const isRunning = isProjectBuilding;

  const start = useCallback(() => {
    if (isRunning || block !== null) return;
    // Документ на подписании: «Собрать» сначала спрашивает (signing-route.md, 12.7).
    routeGuard.run({ docIds: [docId] }, () => {
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
    });
  }, [
    isRunning,
    block,
    routeGuard,
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

/** Id пакета «Собрать все»: UUID v4, и там, где нет `crypto.randomUUID` (страница по http). */
export const newBatchId = (): string => {
  if (typeof crypto.randomUUID === "function") return crypto.randomUUID();
  const bytes = crypto.getRandomValues(new Uint8Array(16));
  bytes[6] = ((bytes[6] ?? 0) & 0x0f) | 0x40;
  bytes[8] = ((bytes[8] ?? 0) & 0x3f) | 0x80;
  const hex = Array.from(bytes, (b) => b.toString(16).padStart(2, "0")).join(
    "",
  );
  return `${hex.slice(0, 8)}-${hex.slice(8, 12)}-${hex.slice(12, 16)}-${hex.slice(16, 20)}-${hex.slice(20)}`;
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
 * Документы без раннера пропускаются: и те, что погашены по доступности, и те,
 * от которых отказался сервер (`no_runner_for_tags`). Остальные собираются, а
 * пропущенные один тост перечисляет по именам с причиной («Презентация (личный
 * раннер на паузе)»). `block` задан, когда собрать нельзя ни один документ проекта.
 */
export const useStartCompileAll = (projectId: string) => {
  const { mutateAsync: triggerCompile } = useTriggerCompile();
  const startStream = useCompileStreamStore((s) => s.start);
  const markPending = useCompileStreamStore((s) => s.markPending);
  const unmarkPending = useCompileStreamStore((s) => s.unmarkPending);
  const handleCompileError = useHandleCompileError();
  const isProjectBuilding = useIsProjectBuilding(projectId);
  const { documents, blockOf } = useProjectBuildBlocks(projectId);
  const { t, i18n } = useTranslation("documents");
  const queryClient = useQueryClient();
  const routeGuard = useRouteEditGuard(projectId);

  const isRunning = isProjectBuilding;
  const block = useMemo(() => {
    if (!documents || documents.length === 0) return null;
    const blocks = documents.map((doc) => blockOf(doc.id));
    if (blocks.some((b) => b === null)) return null;
    return blocks[0] ?? null;
  }, [documents, blockOf]);

  const describeExcluded = useCallback(
    (excluded: readonly { docId: string; block: BuildBlock }[]): string => {
      const lang = i18n.language.startsWith("en") ? "en" : "ru";
      return excluded
        .map(({ docId, block: why }) => {
          const doc = documents?.find((d) => d.id === docId);
          const name = getDocMeta(docId, doc, lang).name;
          const kinds = kindsText(t, why.tags);
          const reason = t(
            `compile.unavailable.causeShort.${why.cause ?? "no_runner"}`,
            { kinds },
          );
          return t("compile.unavailable.excludedItem", { name, reason });
        })
        .join("; ");
    },
    [documents, i18n.language, t],
  );

  const build = useCallback(
    (docIds: readonly string[]) => {
      const excluded: { docId: string; block: BuildBlock }[] = [];
      const buildable: string[] = [];
      for (const docId of docIds) {
        const why = blockOf(docId);
        if (why === null) buildable.push(docId);
        else excluded.push({ docId, block: why });
      }
      const report = () => {
        if (excluded.length === 0) return;
        toast.warning(
          t("compile.unavailable.buildAllExcluded", {
            count: excluded.length,
            list: describeExcluded(excluded),
          }),
          {
            key: "compile-build-all-skipped",
            title: t("compile.unavailable.title"),
            duration: 12_000,
          },
        );
      };
      // Один пакет на команду: в очереди админки её задачи видны одной строкой.
      const batchId = newBatchId();
      // Reserve the project-wide lock synchronously for ALL docs before any
      // POST goes out. This way the button is disabled the same tick the
      // click handler runs, regardless of how the network roundtrips race.
      for (const docId of buildable) markPending(projectId, docId);
      let errorShown = false;
      const posts = buildable.map((docId) =>
        triggerCompile({ projectId, docId, batchId }).then(
          (result) => {
            startStream(projectId, docId, result.compile_id);
          },
          (err: unknown) => {
            unmarkPending(projectId, docId);
            // Сервер отказал «некому собрать»: документ в общий список пропущенных.
            const refusal = blockOfRefusal(err);
            if (refusal !== null) {
              excluded.push({ docId, block: refusal });
              // Опрос доступности отстал от жизни: перечитываем, и кнопки погаснут сами.
              void queryClient.invalidateQueries({
                queryKey: [...runnerKeys.all, "availability"],
              });
              return;
            }
            // For a batch trigger the same setup error fires once per
            // doc; show the toast just for the first.
            if (!errorShown) {
              errorShown = true;
              handleCompileError(err);
            }
          },
        ),
      );
      void Promise.allSettled(posts).then(report);
    },
    [
      blockOf,
      markPending,
      unmarkPending,
      triggerCompile,
      startStream,
      handleCompileError,
      describeExcluded,
      queryClient,
      projectId,
      t,
    ],
  );

  // Одно окно на всю команду с перечнем документов на подписании (signing-route.md, 12.7).
  const startAll = useCallback(
    (docIds: readonly string[]) => {
      if (isRunning || docIds.length === 0) return;
      const buildable = docIds.filter((docId) => blockOf(docId) === null);
      routeGuard.run({ docIds: buildable }, () => {
        build(docIds);
      });
    },
    [isRunning, blockOf, routeGuard, build],
  );

  return { startAll, isRunning, block };
};
