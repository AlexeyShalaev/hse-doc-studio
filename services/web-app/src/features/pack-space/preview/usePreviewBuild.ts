import { useEffect, useMemo, useRef, useState } from "react";
import { useTranslation } from "react-i18next";
import {
  packPreviewPdfUrl,
  usePackFilesRevision,
  usePackOutcome,
  usePackOutcomeInputs,
  usePackPreviewOptions,
  type OutcomeInput,
  type PackOutcome,
  type PackOutcomeRequest,
  type PackPreviewBuild,
  type PackPreviewVariant,
  type PackPreviewExample,
} from "@entities/pack-studio";
import { usePreviewRunner } from "@features/pack-preview";
import {
  INPUTS_SOURCE,
  filesKeyOf,
  previewTarget,
  runKeyOf,
  staleByFiles,
} from "@features/pack-preview/lib/previewRequest";
import { ApiError } from "@shared/api";
import { useSpace } from "../context/SpaceContext";
import { useSituation } from "../context/useSituation";
import { useSpaceNav } from "../context/useSpaceNav";
import { makeReasoner, type Reason } from "../result/reasons";
import { EXAMPLE_PARAM } from "../situation/useSituationDelta";
import { readPreviewBuildSeed } from "./buildSeed";

// Предпросмотр PDF документа по условиям студента (pack-studio-ux.md, 5.4 и 5.5, срез S9). Условия
// берутся из адреса (`i.*`), пример данных из `example`; документ, вариант и имя файла считает
// сервер, клиент только раскладывает условия по запросу сборки (`previewTarget`). Сборка стартует
// сама один раз при открытии; дальше смена условий или файлов только помечает страницу
// устаревшей, а пересобирает её кнопка: так страница не прыгает под руками, пока человек правит.

const EXAMPLE = /^[A-Za-z0-9][A-Za-z0-9_:./-]{0,254}$/;

/** Состояние панели: ровно одно, по нему рисуется весь экран. */
export type PreviewView =
  | { kind: "loading" }
  /** Условия или параметры сборки не пришли. */
  | { kind: "unavailable"; error: unknown; retry: () => void }
  /** Сервер документ в PDF не собирает (например, презентация). */
  | { kind: "noPdf" }
  /** Документа нет в комплекте при этих условиях студента. */
  | { kind: "notInKit"; reason: Reason | null }
  | { kind: "building" }
  | {
      kind: "ready";
      build: PackPreviewBuild;
      pdfUrl: string;
      stale: "conditions" | "files" | null;
    }
  | { kind: "failed"; build: PackPreviewBuild | null; error: unknown }
  | { kind: "cancelled" }
  /** Сейчас идёт предельное число сборок. */
  | { kind: "quota"; limit: number }
  /** Ещё ничего не собиралось (например, отказались от сборки до её начала). */
  | { kind: "idle" };

export type PreviewBuild = {
  view: PreviewView;
  /** Пример данных: выбранный, список и запись выбора в адрес. */
  example: {
    id: string;
    list: readonly PackPreviewExample[];
    broken: string | null;
    set: (id: string) => void;
  };
  /** Варианты документа, если их больше одного. */
  variant: {
    id: string | null;
    list: readonly PackPreviewVariant[];
    set: (id: string) => void;
    noPdf: boolean;
  } | null;
  /** Условия, по которым собирается страница: все условия версии и их значения сейчас. */
  conditions: {
    inputs: readonly OutcomeInput[];
    values: Readonly<Record<string, string>>;
    loaded: boolean;
  };
  /** Собрать (кнопка): есть что собирать и сервер готов принять запрос. */
  canBuild: boolean;
  rebuild: () => void;
  cancel: () => void;
  starting: boolean;
  running: boolean;
  /** Сборка, чей PDF показан или идёт. */
  buildId: string | null;
  resetSituation: () => void;
  setInput: (id: string, value: string) => void;
};

const limitOf = (error: unknown): number =>
  error instanceof ApiError && typeof error.data?.limit === "number"
    ? error.data.limit
    : 2;

export const usePreviewBuild = (docId: string): PreviewBuild => {
  const { workspace, versionRef, location } = useSpace();
  const { t, i18n } = useTranslation("packSpace");
  const situation = useSituation();
  const nav = useSpaceNav();
  const raw = new URLSearchParams(location.search).get(EXAMPLE_PARAM);
  const example = raw !== null && EXAMPLE.test(raw) ? raw : null;
  const [localVariant, setLocalVariant] = useState<string | null>(null);

  const request = useMemo<PackOutcomeRequest>(
    () => ({
      state: "work_tree",
      scenario: situation.caseId,
      example,
      inputs: situation.inputs,
    }),
    [situation.caseId, situation.inputs, example],
  );
  const outcome = usePackOutcome(workspace.id, versionRef, request);
  const inputsQuery = usePackOutcomeInputs(
    workspace.id,
    versionRef,
    "work_tree",
  );
  const options = usePackPreviewOptions(workspace.id, versionRef);
  const filesRevision = usePackFilesRevision(workspace.id);
  const seed = readPreviewBuildSeed(workspace.id, versionRef, docId);
  const runner = usePreviewRunner(workspace.id, versionRef, seed);

  const shown: PackOutcome | undefined = outcome.data;
  // После смены условий пока лежит прежний результат: по нему собирать нельзя.
  const fresh = shown !== undefined && !outcome.isPlaceholderData;
  const opts = options.data;
  const inputList = inputsQuery.data?.inputs;

  const target = useMemo(
    () =>
      opts && shown
        ? previewTarget({
            options: opts,
            document: docId,
            source: INPUTS_SOURCE,
            variantPick: localVariant,
            inputs: shown.inputs,
            example,
            shownExample: shown.example,
            scenarioLang: undefined,
          })
        : null,
    [opts, shown, docId, localVariant, example],
  );
  const filesKey = filesKeyOf({
    revision: shown?.revision ?? "",
    scenarioEtag: "",
    filesRevision,
  });
  const fullKey = target ? runKeyOf(target, filesKey) : "";
  const body = target?.body ?? null;

  const outcomeDoc = shown?.documents.find((doc) => doc.id === docId);
  const inKit = outcomeDoc?.state === "active";
  const exampleId = body?.example ?? opts?.default_example ?? "";
  const exampleError =
    opts?.examples.find((item) => item.id === exampleId)?.error ?? null;
  const startable =
    body !== null && fresh && inKit && exampleError === null && !!opts;

  // Одна автосборка при открытии: дальше сборку запускает только кнопка.
  const auto = useRef(false);
  const { start, attemptedKey, cancel: cancelBuild } = runner;
  useEffect(() => {
    if (!startable || auto.current || attemptedKey !== null) return;
    auto.current = true;
    start(body, fullKey);
  }, [startable, body, fullKey, attemptedKey, start]);

  // Закрытая панель не держит сборку: идущая отменяется, место в очереди освобождается.
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

  const rebuild = () => {
    if (body !== null && fullKey !== "") start(body, fullKey);
  };

  const view = ((): PreviewView => {
    if (options.isPending || outcome.isPending) return { kind: "loading" };
    if (opts === undefined || shown === undefined) {
      return {
        kind: "unavailable",
        error: options.error ?? outcome.error,
        retry: () => {
          void options.refetch();
          void outcome.refetch();
        },
      };
    }
    // Сначала «нет в комплекте»: документ, которого студент не получит, объяснять через PDF незачем.
    if (!inKit) {
      const reasoner = makeReasoner(t, i18n.language, shown, inputList);
      return {
        kind: "notInKit",
        reason: outcomeDoc ? reasoner.why(outcomeDoc.why) : null,
      };
    }
    if (target?.doc == null) return { kind: "noPdf" };
    const { build, builtKey, startError, buildError } = runner;
    // Новая сборка идёт: прежняя страница не показывается, чтобы не выдать старое за новое.
    if (runner.starting) return { kind: "building" };
    if (startError instanceof ApiError && startError.code === "preview_quota") {
      return { kind: "quota", limit: limitOf(startError) };
    }
    if (startError != null) {
      return { kind: "failed", build: null, error: startError };
    }
    if (buildError != null) {
      return { kind: "failed", build: null, error: buildError };
    }
    if (build?.status === "succeeded") {
      const stale =
        builtKey !== null && builtKey !== fullKey
          ? staleByFiles(builtKey, filesKey)
            ? "files"
            : "conditions"
          : null;
      return {
        kind: "ready",
        build,
        pdfUrl: seed?.pdfUrl ?? packPreviewPdfUrl(workspace.id, build.id),
        stale,
      };
    }
    if (build?.status === "failed") {
      return { kind: "failed", build, error: null };
    }
    if (build?.status === "cancelled") return { kind: "cancelled" };
    if (build !== undefined || runner.buildId !== null) {
      return { kind: "building" };
    }
    return startable ? { kind: "building" } : { kind: "idle" };
  })();

  const variants = target?.doc?.variants ?? [];
  const control = inputList?.find((item) => item.id === `variant.${docId}`);
  return {
    view,
    example: {
      id: exampleId,
      list: opts?.examples ?? [],
      broken: exampleError,
      set: (id) => {
        nav.go({
          extra: { [EXAMPLE_PARAM]: id === opts?.default_example ? null : id },
        });
      },
    },
    variant:
      variants.length > 1
        ? {
            id: target?.variant ?? null,
            list: variants,
            noPdf:
              variants.find((item) => item.id === target?.variant)?.pdf ===
              false,
            set: (id) => {
              // Условие «вариант документа» есть у версии: выбор ложится в условия студента,
              // как у выбора в строке документа. Нет: выбор живёт только в этой панели.
              if (control) situation.setInput(control.id, id);
              else setLocalVariant(id);
            },
          }
        : null,
    conditions: {
      inputs: inputList ?? [],
      values: shown?.inputs ?? {},
      loaded: inputList !== undefined && shown !== undefined,
    },
    canBuild: startable && !runner.starting && !runner.running,
    rebuild,
    cancel: runner.cancel,
    starting: runner.starting,
    running: runner.running,
    buildId: runner.buildId,
    resetSituation: situation.reset,
    setInput: situation.setInput,
  };
};
