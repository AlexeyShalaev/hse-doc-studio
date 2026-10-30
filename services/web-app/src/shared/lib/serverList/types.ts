import type { z } from "zod";
import type { PickerItemSchema, PickerPageSchema } from "@shared/api";

// Формы ответов серверных списков (единый контракт списков админ-API и пикеров).
// Типы пикера выводятся из схем zod в shared/api, они же сверяются с
// contracts/server/fixtures; схемы конкретных ресурсов живут в entities.

/** Ограниченный список: окно limit/offset и общее число под теми же фильтрами. */
export type ListPage<T> = {
  items: T[];
  total: number;
  limit: number;
  offset: number;
};

/**
 * Журнал с дописыванием (аудит, очередь): курсор непрозрачный, null на
 * последней странице. Оценка числа есть только без фильтров.
 */
export type CursorPage<T> = {
  items: T[];
  next_cursor: string | null;
  total_estimate: number | null;
};

/** Строка пикера: что выбрать и одна строка подробностей (почта, адрес, метки). */
export type PickerItem = z.infer<typeof PickerItemSchema>;
export type PickerKind = PickerItem["kind"];

/** Ответ пикера: первые совпадения; has_more значит «уточните поиск». */
export type PickerPage = z.infer<typeof PickerPageSchema>;

/** Значения параметров запроса: повтор параметра для нескольких значений. */
export type ListRequestParams = Record<string, string | number | string[]>;

/** Размеры страницы, которые предлагает переключатель. */
export const PAGE_SIZES: readonly number[] = [25, 50, 100, 200];
export const DEFAULT_PAGE_SIZE = 50;
/** Сколько строк просит пикер; сервер больше не отдаёт. */
export const PICKER_LIMIT = 20;
/** Пауза в наборе, после которой уходит запрос поиска. */
export const SEARCH_DEBOUNCE_MS = 300;
/** Длиннее строку поиска сервер не примет (422). */
export const SEARCH_MAX_LENGTH = 200;
