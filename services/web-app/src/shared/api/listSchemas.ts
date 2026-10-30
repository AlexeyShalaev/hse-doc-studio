import { z } from "zod";

// Общие формы серверных списков (единый контракт списков и пикеров). Строки
// каждого ресурса описывают его схемы в entities, здесь только обёртки.

/** Ограниченный список: {items, total, limit, offset}. */
export const listPageOf = <T extends z.ZodType>(item: T) =>
  z.strictObject({
    items: z.array(item),
    total: z.number().int(),
    limit: z.number().int(),
    offset: z.number().int(),
  });

/** Журнал с курсором: total_estimate только без фильтров, иначе null. */
export const cursorPageOf = <T extends z.ZodType>(item: T) =>
  z.strictObject({
    items: z.array(item),
    next_cursor: z.string().nullable(),
    total_estimate: z.number().int().nullable().optional(),
  });

export const PickerItemSchema = z.strictObject({
  kind: z.enum(["user", "org", "group", "project", "runner"]),
  id: z.string(),
  name: z.string(),
  detail: z.string().nullable(),
});

/** Пикер: первые совпадения; has_more значит «уточните поиск». */
export const PickerPageSchema = z.strictObject({
  items: z.array(PickerItemSchema),
  has_more: z.boolean(),
});
