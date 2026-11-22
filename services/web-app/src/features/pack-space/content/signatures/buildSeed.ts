import type { PackPreviewOptions, PackVersionRef } from "@entities/pack-studio";
import type { PreviewRunnerSeed } from "@features/pack-preview";
import {
  INPUTS_SOURCE,
  previewTarget,
} from "@features/pack-preview/lib/previewRequest";

// Готовая сборка документа, подложенная до первого кадра: только для галереи и тестов, где сервера
// нет. Рабочий экран сюда ничего не кладёт и собирает PDF сам (`useDocumentPdf`).

export type DocumentBuildSeed = PreviewRunnerSeed & {
  /** Адрес PDF вместо адреса сервера (в галерее страница лежит в самой записи). */
  pdfUrl?: string;
};

const seeds = new Map<string, DocumentBuildSeed>();
const idOf = (workspaceId: string, ref: PackVersionRef, docId: string) =>
  [workspaceId, ref.pack, ref.template, ref.version, docId].join("\u0000");

export const seedDocumentBuild = (
  workspaceId: string,
  ref: PackVersionRef,
  docId: string,
  seed: DocumentBuildSeed | null,
): void => {
  const id = idOf(workspaceId, ref, docId);
  if (seed === null) seeds.delete(id);
  else seeds.set(id, seed);
};

export const readDocumentBuildSeed = (
  workspaceId: string,
  ref: PackVersionRef,
  docId: string,
): DocumentBuildSeed | null => seeds.get(idOf(workspaceId, ref, docId)) ?? null;

/** Ключ запроса сборки документа при этих условиях студента (тот же, что считает `useDocumentPdf`). */
export const documentBuildKey = (
  options: PackPreviewOptions,
  docId: string,
  inputs: Readonly<Record<string, string>>,
): string =>
  previewTarget({
    options,
    document: docId,
    source: INPUTS_SOURCE,
    variantPick: null,
    inputs,
    example: null,
    shownExample: null,
    scenarioLang: undefined,
  }).key;
