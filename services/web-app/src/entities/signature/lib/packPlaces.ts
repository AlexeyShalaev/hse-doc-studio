import type {
  PackDateMarkResponse,
  PackPlaceResponse,
  PlacementOrigin,
} from "@shared/api/types";

// Место подписи из шаблона (docs/design/signing-route.md, 15.3): у слота каталога своё место на
// каждом документе (`placements` пака), а общее `default_placement` достаётся документам без
// своей записи. Сервер отдаёт оба в рантайм-слоте; каталожный слот (фолбэк без рантайм-слотов)
// знает только общее место.

type PackSlot = {
  default_placement: PackPlaceResponse;
  default_placements?: Record<string, PackPlaceResponse> | undefined;
  default_dates?: Record<string, PackDateMarkResponse[]> | undefined;
};

/** Место слота на документе из шаблона: своё место документа, иначе общее место слота. */
export const packPlaceOf = (slot: PackSlot, docId: string): PackPlaceResponse =>
  slot.default_placements?.[docId] ?? slot.default_placement;

/** Метки даты слота на документе из шаблона; пусто, если шаблон их не задаёт. */
export const packDatesOf = (
  slot: PackSlot,
  docId: string,
): PackDateMarkResponse[] => slot.default_dates?.[docId] ?? [];

/**
 * Пометка места (15.7): `template` место как в шаблоне (в том числе затравка, которую никто не
 * трогал), `changed` место изменено и его можно вернуть, null пометки нет (сервер не знает места
 * в шаблоне или не прислал происхождение).
 */
export type PlaceMark = "template" | "changed";

export const placeMarkOf = (
  placement:
    { origin?: PlacementOrigin; preset_available?: boolean } | undefined,
): PlaceMark | null => {
  if (!placement?.preset_available || placement.origin === undefined)
    return null;
  return placement.origin === "manual" ? "changed" : "template";
};
