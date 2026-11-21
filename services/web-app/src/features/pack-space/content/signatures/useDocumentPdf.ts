import { useEffect, useMemo, useRef } from "react";
import {
  packPreviewPdfUrl,
  usePackPreviewOptions,
  type PackPreviewBuild,
  type PackVersionRef,
} from "@entities/pack-studio";
import {
  documentFits,
  effectiveCombination,
  exampleOf,
  usePreviewRunner,
} from "@features/pack-preview";
import {
  INPUTS_SOURCE,
  previewTarget,
} from "@features/pack-outcome/lib/previewRequest";
import { readDocumentBuildSeed } from "./buildSeed";

// PDF документа для расстановки подписей (pack-studio-ux.md, 5.5, срез S8c): человек ничего не
// собирает сам. Документ собирается при открытии «Подписей» на условиях студента с экрана
// (`i.*` адреса), сервер считает вариант и имя файла. Правки мест пишут в описание версии, но PDF
// не пересобирают: рамки двигаются по готовой странице. Новая сборка нужна только при смене условий
// или по кнопке «Собрать ещё раз».

export type DocumentPdf =
  | { state: "loading" }
  /** Сервер документ не собирает (например, презентация): PDF не будет. */
  | { state: "none" }
  /** Документа нет в комплекте при этих условиях студента. */
  | { state: "notInKit" }
  | { state: "building"; cancel: () => void }
  | {
      state: "failed";
      error: unknown;
      build: PackPreviewBuild | null;
      retry: () => void;
    }
  | {
      state: "ready";
      build: PackPreviewBuild;
      pdfUrl: string;
      /** Язык документа в этой сборке: месяц в примере даты. */
      lang: string;
      rebuild: () => void;
    };

export const useDocumentPdf = (
  workspaceId: string,
  versionRef: PackVersionRef,
  docId: string,
  inputs: Readonly<Record<string, string>>,
): DocumentPdf => {
  const options = usePackPreviewOptions(workspaceId, versionRef);
  const seed = readDocumentBuildSeed(workspaceId, versionRef, docId);
  const runner = usePreviewRunner(workspaceId, versionRef, seed);
  const data = options.data;

  const target = useMemo(
    () =>
      data
        ? previewTarget({
            options: data,
            document: docId,
            source: INPUTS_SOURCE,
            variantPick: null,
            inputs,
            example: null,
            shownExample: null,
            scenarioLang: undefined,
          })
        : null,
    [data, docId, inputs],
  );
  const fits = useMemo(() => {
    if (!data || !target?.doc) return true;
    return documentFits(
      target.doc,
      effectiveCombination(data, exampleOf(data, null), {
        ...(target.body?.combination ?? {}),
      }),
    );
  }, [data, target]);

  const key = target?.key ?? "";
  const body = target?.body ?? null;
  const { start, attemptedKey, cancel: cancelBuild } = runner;
  useEffect(() => {
    if (body === null || !fits || key === "" || attemptedKey === key) return;
    start(body, key);
  }, [body, fits, key, attemptedKey, start]);

  // Закрытый экран не держит сборку: идущая отменяется, место в очереди освобождается.
  const live = useRef({ running: false, cancel: cancelBuild });
  useEffect(() => {
    live.current = { running: runner.running, cancel: cancelBuild };
  }, [runner.running, cancelBuild]);
  useEffect(
    () => () => {
      if (live.current.running) live.current.cancel();
    },
    [],
  );

  if (options.isPending) return { state: "loading" };
  if (data === undefined) {
    return {
      state: "failed",
      error: options.error,
      build: null,
      retry: () => void options.refetch(),
    };
  }
  if (target?.doc == null) return { state: "none" };
  if (!fits) return { state: "notInKit" };

  const retry = () => {
    if (body !== null) start(body, key);
  };
  const { build, builtKey } = runner;
  if (build?.status === "succeeded" && builtKey === key) {
    return {
      state: "ready",
      build,
      pdfUrl: seed?.pdfUrl ?? packPreviewPdfUrl(workspaceId, build.id),
      lang: build.combination.lang ?? inputs.lang ?? "ru",
      rebuild: retry,
    };
  }
  const failedBuild =
    build !== undefined &&
    builtKey === key &&
    (build.status === "failed" || build.status === "cancelled");
  if (runner.startError != null) {
    return { state: "failed", error: runner.startError, build: null, retry };
  }
  if (failedBuild) {
    return { state: "failed", error: null, build, retry };
  }
  return { state: "building", cancel: runner.cancel };
};
