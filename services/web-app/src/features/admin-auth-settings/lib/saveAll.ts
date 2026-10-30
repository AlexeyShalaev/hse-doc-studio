import { failureCode } from "@shared/api";

export type SaveStep = { run: () => Promise<unknown>; done: () => void };

/**
 * Сохранить несколько частей страницы одновременно. Удачные части сбрасывают
 * свои правки, неудачные остаются в черновике. Возвращает код первой ошибки
 * или null, если всё сохранилось.
 */
export const settleSaves = async (
  steps: readonly (SaveStep | false)[],
): Promise<string | null> => {
  const active = steps.filter((s): s is SaveStep => s !== false);
  const results = await Promise.allSettled(active.map((s) => s.run()));
  let failure: string | null = null;
  results.forEach((result, i) => {
    if (result.status === "fulfilled") active[i]?.done();
    else failure ??= failureCode(result.reason);
  });
  return failure;
};
