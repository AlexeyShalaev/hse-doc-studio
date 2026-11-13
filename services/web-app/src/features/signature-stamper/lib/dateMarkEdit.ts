import type { DateMarkInput } from "@entities/signature";
import type { PlacementResponse } from "@shared/api/types";

// Правка меток даты слота документа (docs/design/signing-route.md, 14.2): сервер принимает список
// меток целиком (`PUT .../dates`), поэтому каждое действие строит новый список из нынешнего.

/** Место рамки на странице, мм. */
export type DateMarkPlace = {
  x_mm: number;
  y_mm: number;
  width_mm: number;
  height_mm: number;
};

/** Тело сохранения без `confirm_reset`: его добавляет подтверждение сброса подписей. */
export type DateMarksSave = {
  dates: DateMarkInput[];
  /** `{date}` ставит ручную дату, null убирает её; без поля дата не меняется. */
  signed_at?: { date: string } | null;
};

// Рамка новой метки: строка «13.11.2026» шестым кеглем и крупнее.
const NEW_WIDTH_MM = 28;
const NEW_HEIGHT_MM = 6;
// Отступ новой метки под рамкой подписи.
const GAP_MM = 2;

export const marksOf = (
  placement: PlacementResponse | undefined,
): DateMarkInput[] =>
  (placement?.dates ?? []).map((mark) => ({
    id: mark.id,
    page: mark.page,
    x_mm: mark.x_mm,
    y_mm: mark.y_mm,
    width_mm: mark.width_mm,
    height_mm: mark.height_mm,
    format: mark.format,
    align: mark.align,
  }));

/**
 * Новая метка на странице `page`: под рамкой подписи, если подпись на этой же странице, иначе
 * ниже прошлой метки или в середине листа. Формат «13.11.2026», по центру.
 */
export const newDateMark = (
  placement: PlacementResponse | undefined,
  page: number,
  signatureHeightMm: number,
): DateMarkInput => {
  const onPage = (placement?.dates ?? []).filter((m) => m.page === page);
  const last = onPage.at(-1);
  const below =
    last !== undefined
      ? { x_mm: last.x_mm, y_mm: last.y_mm + last.height_mm + GAP_MM }
      : placement?.enabled && placement.page === page
        ? {
            x_mm: placement.x_mm,
            y_mm: placement.y_mm + signatureHeightMm + GAP_MM,
          }
        : { x_mm: 90, y_mm: 140 };
  return {
    id: null,
    page,
    x_mm: Math.round(below.x_mm * 10) / 10,
    // Лист A4 по высоте 297 мм: рамка не уходит за нижний край.
    y_mm: Math.round(Math.min(below.y_mm, 297 - NEW_HEIGHT_MM - 5) * 10) / 10,
    width_mm: NEW_WIDTH_MM,
    height_mm: NEW_HEIGHT_MM,
    format: "date_numeric",
    align: "center",
  };
};

export const replaceMark = (
  marks: readonly DateMarkInput[],
  index: number,
  patch: Partial<DateMarkInput>,
): DateMarkInput[] =>
  marks.map((mark, i) => (i === index ? { ...mark, ...patch } : mark));

export const removeMark = (
  marks: readonly DateMarkInput[],
  index: number,
): DateMarkInput[] => marks.filter((_, i) => i !== index);

const round = (mm: number): number => Math.round(mm * 100) / 100;

/** Место после перетаскивания: до сотых долей миллиметра, как у подписи. */
export const roundPlace = (place: DateMarkPlace): DateMarkPlace => ({
  x_mm: round(place.x_mm),
  y_mm: round(place.y_mm),
  width_mm: round(place.width_mm),
  height_mm: round(place.height_mm),
});
