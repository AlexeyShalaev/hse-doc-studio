import type { PackPlaceEntry, PackSignatureSlot } from "@entities/pack-studio";

// Места подписей простыми словами (pack-studio-ux.md, 5.5 и 6): где стоит подпись в документе и
// как она держится. Чистые функции без React: слова берёт компонент, здесь только выбор случая.

/** Как подпись стоит в этом документе. */
export type PlaceStatus = "own" | "shared" | "missing";

/** Свой случай документа, общее место подписи или места в этом PDF нет. `null`: подпись документа не касается. */
export const placeStatusOf = (slot: PackSignatureSlot): PlaceStatus | null => {
  const frame = slot.document;
  if (frame === null) return null;
  if (frame.box === null) return "missing";
  return frame.kind === "place" ? "own" : "shared";
};

/** Подписи, которые бывают в документе (сервер называет их `applies_to`). */
export const slotsForDocument = (
  slots: readonly PackSignatureSlot[],
  docId: string,
): PackSignatureSlot[] =>
  slots.filter((slot) => slot.applies_to.includes(docId));

/** Как место записано в версии: на странице (в миллиметрах) или по строке текста документа. */
export type EntryKind = "page" | "text";

export const entryKind = (entry: PackPlaceEntry): EntryKind =>
  entry.source === "mm" ? "page" : "text";

/** Страница, на которой стоит место; для места по строке текста берётся запасная. */
export const entryPage = (entry: PackPlaceEntry): number | null =>
  entry.source === "mm" ? entry.page : (entry.fallback?.page ?? null);

/** Миллиметры без хвоста: 110, 12.5. */
export const mm = (value: number): string =>
  String(Math.round(value * 10) / 10);

/** Что стоит с документом в версии: свои места, общие, нет места. Для сводки раздела. */
export type DocumentPlaces = { docId: string; status: "own" | "shared" };

export const documentPlacesOf = (slot: PackSignatureSlot): DocumentPlaces[] =>
  slot.applies_to.map((docId) => ({
    docId,
    status: docId in slot.places ? "own" : "shared",
  }));
