export type Rect = { top: number; left: number; width: number; height: number };
export type Viewport = { width: number; height: number };
export type Placement =
  "top" | "bottom" | "left" | "right" | "center" | "sheet";
export type PopoverBox = { top: number; left: number; placement: Placement };

/** Отступ подсветки вокруг элемента и зазор до подсказки. */
export const SPOT_PADDING = 6;
const GAP = 12;
const MARGIN = 12;
/** Уже этого окна подсказка становится нижней шторкой во всю ширину. */
export const SHEET_BELOW = 560;

const clamp = (value: number, min: number, max: number): number =>
  Math.min(Math.max(value, min), Math.max(min, max));

/** Прямоугольник подсветки: элемент с полями, обрезанный по окну. */
export const spotlightRect = (target: Rect, viewport: Viewport): Rect => {
  const top = Math.max(target.top - SPOT_PADDING, 0);
  const left = Math.max(target.left - SPOT_PADDING, 0);
  const bottom = Math.min(
    target.top + target.height + SPOT_PADDING,
    viewport.height,
  );
  const right = Math.min(
    target.left + target.width + SPOT_PADDING,
    viewport.width,
  );
  return {
    top,
    left,
    width: Math.max(right - left, 0),
    height: Math.max(bottom - top, 0),
  };
};

/**
 * Где поставить подсказку размера `box` рядом с подсвеченным `spot`.
 * Порядок: снизу, сверху, справа, слева; не влезла никуда — по центру окна.
 * Нет элемента — по центру; узкое окно — шторка снизу.
 */
export const placePopover = (
  spot: Rect | null,
  box: { width: number; height: number },
  viewport: Viewport,
): PopoverBox => {
  if (viewport.width < SHEET_BELOW) {
    return {
      top: viewport.height - box.height - MARGIN,
      left: MARGIN,
      placement: "sheet",
    };
  }
  const centered: PopoverBox = {
    top: clamp((viewport.height - box.height) / 2, MARGIN, viewport.height),
    left: clamp((viewport.width - box.width) / 2, MARGIN, viewport.width),
    placement: "center",
  };
  if (!spot) return centered;
  const fitsX = (left: number) =>
    left >= MARGIN && left + box.width <= viewport.width - MARGIN;
  const fitsY = (top: number) =>
    top >= MARGIN && top + box.height <= viewport.height - MARGIN;
  const alignedLeft = clamp(
    spot.left + spot.width / 2 - box.width / 2,
    MARGIN,
    viewport.width - box.width - MARGIN,
  );
  const alignedTop = clamp(
    spot.top + spot.height / 2 - box.height / 2,
    MARGIN,
    viewport.height - box.height - MARGIN,
  );
  const below = spot.top + spot.height + GAP;
  if (fitsY(below))
    return { top: below, left: alignedLeft, placement: "bottom" };
  const above = spot.top - GAP - box.height;
  if (fitsY(above)) return { top: above, left: alignedLeft, placement: "top" };
  const right = spot.left + spot.width + GAP;
  if (fitsX(right)) return { top: alignedTop, left: right, placement: "right" };
  const left = spot.left - GAP - box.width;
  if (fitsX(left)) return { top: alignedTop, left, placement: "left" };
  return centered;
};
