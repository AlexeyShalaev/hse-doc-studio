import type { PackVersionRef } from "@entities/pack-studio";
import type { PreviewRunnerSeed } from "@features/pack-preview";

// Готовая сборка документа, подложенная до первого кадра: только для галереи и тестов, где сервера
// нет. Рабочий экран сюда ничего не кладёт и собирает PDF сам (`usePreviewBuild`).

export type PreviewBuildSeed = PreviewRunnerSeed & {
  /** Адрес PDF вместо адреса сервера (в галерее страница лежит в самой записи). */
  pdfUrl?: string;
};

const seeds = new Map<string, PreviewBuildSeed>();
const idOf = (workspaceId: string, ref: PackVersionRef, docId: string) =>
  [workspaceId, ref.pack, ref.template, ref.version, docId].join("\u0000");

export const seedPreviewBuild = (
  workspaceId: string,
  ref: PackVersionRef,
  docId: string,
  seed: PreviewBuildSeed | null,
): void => {
  const id = idOf(workspaceId, ref, docId);
  if (seed === null) seeds.delete(id);
  else seeds.set(id, seed);
};

export const readPreviewBuildSeed = (
  workspaceId: string,
  ref: PackVersionRef,
  docId: string,
): PreviewBuildSeed | null => seeds.get(idOf(workspaceId, ref, docId)) ?? null;
