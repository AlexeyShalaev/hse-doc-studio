import type {
  PackDateEntryResponse,
  PackDateMarkResponse,
  PackPlaceEntryResponse,
  PackPlaceResponse,
  PlaceAnchorResponse,
  PlaceSource,
  PlacementOrigin,
} from "@shared/api/types";

// Место подписи из шаблона (docs/design/signing-route.md, 15.3): у слота каталога своё место на
// каждом документе (`placements` пака), а общее `default_placement` достаётся документам без
// своей записи. Сервер отдаёт оба в рантайм-слоте; каталожный слот (фолбэк без рантайм-слотов)
// знает только общее место. Запись документа бывает в мм или на строке шаблона (якорь, 15.17.7):
// место на якоре считает сервер по сборке, интерфейсу без сборки достаётся только запасное место.

type PackSlot = {
  default_placement: PackPlaceResponse;
  default_placements?: Record<string, PackPlaceEntryResponse> | undefined;
  default_dates?: Record<string, PackDateEntryResponse[]> | undefined;
};

/** Запись места пака у документа как есть (в мм или на якоре); undefined, если своей записи нет. */
export const packEntryOf = (
  slot: PackSlot,
  docId: string,
): PackPlaceEntryResponse | undefined => slot.default_placements?.[docId];

/**
 * Место слота на документе из шаблона в мм, как `place_for` сервера: запись в мм, запасное место
 * записи на якоре, иначе общее место слота.
 */
export const packPlaceOf = (
  slot: PackSlot,
  docId: string,
): PackPlaceResponse => {
  const entry = packEntryOf(slot, docId);
  if (entry === undefined) return slot.default_placement;
  if (entry.source === "anchor")
    return entry.fallback ?? slot.default_placement;
  return {
    page: entry.page,
    x_mm: entry.x_mm,
    y_mm: entry.y_mm,
    width_mm: entry.width_mm,
  };
};

/**
 * Метки даты слота на документе из шаблона в мм; метка на якоре даёт своё запасное место, без него
 * пропускается. Пусто, если шаблон их не задаёт.
 */
export const packDatesOf = (
  slot: PackSlot,
  docId: string,
): PackDateMarkResponse[] =>
  (slot.default_dates?.[docId] ?? []).flatMap(
    (mark): PackDateMarkResponse[] => {
      if (mark.source === "mm") {
        const { source: _source, ...place } = mark;
        return [place];
      }
      return mark.fallback === null
        ? []
        : [{ ...mark.fallback, format: mark.format, align: mark.align }];
    },
  );

/** У пары есть место пака в мм (запись в мм или запасное место записи на якоре): оно встанет и без якорей. */
export const packHasMmPlace = (slot: PackSlot, docId: string): boolean => {
  const entry = packEntryOf(slot, docId);
  return (
    entry === undefined || entry.source === "mm" || entry.fallback !== null
  );
};

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

/**
 * Место как в шаблоне стоит на строке шаблона (`source: anchor`, 15.17.14): уточнение пометки
 * «Место из шаблона». Только когда строка в источнике подписи найдена: пока якоря сборки
 * неизвестны, место пака на якоре стоит на запасном месте в мм, и это просто «Место из шаблона».
 */
export const placeOnLine = (
  placement:
    | {
        origin?: PlacementOrigin;
        preset_available?: boolean;
        source?: PlaceSource | null;
        anchor?: PlaceAnchorResponse | null;
      }
    | undefined,
): boolean =>
  placeMarkOf(placement) === "template" &&
  placement?.source === "anchor" &&
  placement.anchor?.state === "found";

/**
 * Подсказка у пары, чьё место пака на якоре (15.17.8, 15.17.11, 15.17.14):
 * - `missing`: якоря сборки известны, а строки для подписи в документе нет: место не ставится, и
 *   «Вернуть место из шаблона» ответило бы 409 `anchor_missing`;
 * - `own_pdf`: документ заменён своим PDF, строк шаблона у него нет, место ставит человек;
 * - `unknown`: якоря неизвестны, а запасного места в мм нет. Видна, пока места нет или оно
 *   изменено: вернуть его нечем (409 `anchors_unknown`).
 * null: подсказки нет. Подсказка стоит вместо кнопки «Вернуть место из шаблона».
 */
export type AnchorNote = "missing" | "unknown" | "own_pdf";

export const anchorNoteOf = (
  placement:
    | {
        enabled?: boolean;
        origin?: PlacementOrigin;
        anchor?: PlaceAnchorResponse | null;
      }
    | undefined,
  opts: { ownPdf?: boolean; hasMmPlace?: boolean } = {},
): AnchorNote | null => {
  const anchor = placement?.anchor;
  if (!anchor) return null;
  if (anchor.state === "missing") return "missing";
  if (anchor.state === "found") return null;
  if (opts.ownPdf === true) return "own_pdf";
  if (opts.hasMmPlace === true) return null;
  return !placement.enabled || placement.origin === "manual" ? "unknown" : null;
};
