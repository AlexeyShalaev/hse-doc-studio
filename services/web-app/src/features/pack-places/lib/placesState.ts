import type { DateMarkInput } from "@entities/signature";
import type {
  PackFrameDate,
  PackMarkBox,
  PackPlaceBox,
  PackPlaceOp,
  PackSignatures,
  PackSignatureSlot,
} from "@entities/pack-studio";
import type { DateMarksSave } from "@features/signature-stamper";
import type {
  PlacementResponse,
  SignatureSlotDefResponse,
  SignaturesStateResponse,
  SlotInfoResponse,
} from "@shared/api/types";

// Места подписей пака на PDF предпросмотра (template-studio.md, 5.6, срез T9): модель сервера
// переводится в состояние, которое понимает редактор мест проекта (`PdfStampEditor`), а его жесты и
// правки меток даты обратно в правки мест пака. Модуль чистый.

/** Рамка без картинки подписи: заглушка с именем слота в типичной пропорции 3:1. */
const PLACEHOLDER: SlotInfoResponse = {
  png_path: null,
  natural_width_px: 300,
  natural_height_px: 100,
  signing_identity_id: null,
  sign_mode: "image",
  sign_reason: "",
  signer: null,
};

/** Высота заглушки, мм: новая метка даты встаёт под рамкой. */
export const placeholderHeightMm = (widthMm: number): number => widthMm / 3;

/** Метки даты в состоянии редактора: только те, что есть в этой сборке; id `i<индекс в YAML>`. */
const dateId = (date: PackFrameDate): string => `i${String(date.index)}`;

export const shownDates = (slot: PackSignatureSlot): PackFrameDate[] =>
  (slot.document?.dates ?? []).filter((date) => date.box !== null);

export type PlacesStamperState = {
  document: string;
  slotDefs: SignatureSlotDefResponse[];
  state: SignaturesStateResponse;
  /** Слоты с местом по умолчанию: их рамки бледные. */
  muted: Set<string>;
};

/** Место слота в состоянии редактора: рамка этой сборки и её метки даты. */
export const placementOf = (slot: PackSignatureSlot): PlacementResponse => {
  const box = slot.document?.box ?? null;
  return {
    enabled: box !== null,
    page: box?.page ?? 1,
    x_mm: box?.x_mm ?? 0,
    y_mm: box?.y_mm ?? 0,
    width_mm: box?.width_mm ?? 40,
    dates: shownDates(slot).map((date) => ({
      id: dateId(date),
      page: date.box?.page ?? 1,
      x_mm: date.box?.x_mm ?? 0,
      y_mm: date.box?.y_mm ?? 0,
      width_mm: date.box?.width_mm ?? 0,
      height_mm: date.box?.height_mm ?? 0,
      format: date.box?.format ?? "date_numeric",
      align: date.box?.align ?? "center",
      text: null,
    })),
  };
};

/**
 * Состояние редактора мест для документа сборки. `labelOf` подписывает рамку: у места по умолчанию
 * вызывающий добавляет пометку.
 */
export const stamperStateOf = (
  data: PackSignatures,
  labelOf: (slot: PackSignatureSlot) => Record<string, string>,
): PlacesStamperState | null => {
  const document = data.build?.document;
  if (document === undefined) return null;
  const slots = data.slots.filter((slot) => slot.document !== null);
  return {
    document,
    slotDefs: slots.map((slot) => ({
      id: slot.id,
      label: labelOf(slot),
      applies_to: [document],
      default_placement: { page: 1, x_mm: 0, y_mm: 0, width_mm: 40 },
    })),
    state: {
      slots: Object.fromEntries(slots.map((slot) => [slot.id, PLACEHOLDER])),
      placements: {
        [document]: Object.fromEntries(
          slots.map((slot) => [slot.id, placementOf(slot)]),
        ),
      },
    },
    muted: new Set(
      slots
        .filter((slot) => slot.document?.kind === "default")
        .map((slot) => slot.id),
    ),
  };
};

/** Метки даты слота в том виде, в каком их правит `SlotDateMarks` (список целиком). */
export const marksBefore = (slot: PackSignatureSlot): DateMarkInput[] =>
  (placementOf(slot).dates ?? []).map((mark) => ({
    id: mark.id,
    page: mark.page,
    x_mm: mark.x_mm,
    y_mm: mark.y_mm,
    width_mm: mark.width_mm,
    height_mm: mark.height_mm,
    format: mark.format,
    align: mark.align,
  }));

/** Рамка та же с точностью до округления сервера (1 мм): щелчок без сдвига не пишет файл. */
export const sameBox = (a: PackPlaceBox, b: PackPlaceBox): boolean =>
  a.page === b.page &&
  Math.abs(a.x_mm - b.x_mm) < 0.5 &&
  Math.abs(a.y_mm - b.y_mm) < 0.5 &&
  Math.abs(a.width_mm - b.width_mm) < 0.5;

/** Перетаскивание рамки слота: место документа (рамка по умолчанию тоже становится своей записью). */
export const placeOpFrom = (
  slot: PackSignatureSlot,
  document: string,
  patch: { x_mm?: number; y_mm?: number; width_mm?: number; page?: number },
): PackPlaceOp | null => {
  const box = slot.document?.box;
  if (!box) return null;
  const next: PackPlaceBox = {
    page: patch.page ?? box.page,
    x_mm: patch.x_mm ?? box.x_mm,
    y_mm: patch.y_mm ?? box.y_mm,
    width_mm: patch.width_mm ?? box.width_mm,
  };
  if (sameBox(next, box)) return null;
  return { op: "set_place", slot: slot.id, doc: document, box: next };
};

const markOf = (mark: DateMarkInput): PackMarkBox => ({
  page: mark.page,
  x_mm: mark.x_mm,
  y_mm: mark.y_mm,
  width_mm: mark.width_mm,
  height_mm: mark.height_mm,
  format: mark.format,
  align: mark.align,
});

const sameMark = (a: DateMarkInput, b: DateMarkInput): boolean =>
  a.page === b.page &&
  a.format === b.format &&
  a.align === b.align &&
  Math.abs(a.x_mm - b.x_mm) < 0.5 &&
  Math.abs(a.y_mm - b.y_mm) < 0.5 &&
  Math.abs(a.width_mm - b.width_mm) < 0.5 &&
  Math.abs(a.height_mm - b.height_mm) < 0.5;

const indexOf = (id: string | null): number | null =>
  id !== null && /^i\d+$/.test(id) ? Number(id.slice(1)) : null;

/**
 * Правка меток даты из панели (`SlotDateMarks` отдаёт список целиком) в одну правку пака: новая метка,
 * убранная метка или изменённая метка по индексу в YAML.
 */
export const dateOpFrom = (
  slotId: string,
  document: string,
  before: readonly DateMarkInput[],
  save: DateMarksSave,
): PackPlaceOp | null => {
  const after = save.dates;
  const added = after.find((mark) => mark.id === null);
  if (added) {
    return {
      op: "add_date",
      slot: slotId,
      doc: document,
      mark: markOf(added),
    };
  }
  const removed = before.find(
    (mark) => !after.some((next) => next.id === mark.id),
  );
  const removedIndex = removed ? indexOf(removed.id) : null;
  if (removedIndex !== null) {
    return {
      op: "remove_date",
      slot: slotId,
      doc: document,
      index: removedIndex,
    };
  }
  for (const mark of after) {
    const prev = before.find((item) => item.id === mark.id);
    const index = indexOf(mark.id);
    if (prev && index !== null && !sameMark(prev, mark)) {
      return {
        op: "set_date",
        slot: slotId,
        doc: document,
        index,
        mark: markOf(mark),
      };
    }
  }
  return null;
};

/** Перетаскивание метки даты на странице: индекс в списке редактора переводится в индекс YAML. */
export const dateMoveOpFrom = (
  slot: PackSignatureSlot,
  document: string,
  shownIndex: number,
  place: { x_mm: number; y_mm: number; width_mm: number; height_mm: number },
): PackPlaceOp | null => {
  const date = shownDates(slot)[shownIndex];
  const box = date?.box;
  if (!date || !box) return null;
  const mark: PackMarkBox = { ...box, ...place };
  const same =
    Math.abs(mark.x_mm - box.x_mm) < 0.5 &&
    Math.abs(mark.y_mm - box.y_mm) < 0.5 &&
    Math.abs(mark.width_mm - box.width_mm) < 0.5 &&
    Math.abs(mark.height_mm - box.height_mm) < 0.5;
  if (same) return null;
  return {
    op: "set_date",
    slot: slot.id,
    doc: document,
    index: date.index,
    mark,
  };
};

/** Строки даты сборки этого слота, на которые ещё нет метки документа. */
export const freeDateAnchors = (
  slot: PackSignatureSlot,
  dateAnchors: readonly string[],
): string[] => {
  const used = new Set(
    (slot.document?.dates ?? [])
      .map((date) =>
        date.entry.source === "anchor" ? date.entry.anchor : null,
      )
      .filter((anchor): anchor is string => anchor !== null),
  );
  return dateAnchors.filter(
    (anchor) => anchor.startsWith(`${slot.id}.`) && !used.has(anchor),
  );
};

/** Как стоит место документа: на строке шаблона, на запасном месте, строки нет, в мм. */
export type Binding = "line" | "fallback" | "missing" | "mm";

export const bindingOf = (slot: PackSignatureSlot): Binding => {
  const frame = slot.document;
  if (!frame || frame.entry.source === "mm") return "mm";
  if (frame.anchor?.state === "found") return "line";
  if (frame.anchor?.state === "missing") return "missing";
  return "fallback";
};
