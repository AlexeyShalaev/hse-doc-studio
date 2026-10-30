import type { ListQueryState } from "./useListQueryState";

/**
 * Нужна ли строка листания под коротким списком-карточками (провайдеры).
 * Пока всё помещается на одну страницу самого малого размера, листать нечего
 * и выбирать размер незачем: строка «1–2 из 2» только шумит.
 */
export const needsPager = (
  total: number,
  state: Pick<ListQueryState, "page" | "pageSizes">,
): boolean => state.page > 0 || total > Math.min(...state.pageSizes);
