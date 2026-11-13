// 1 PDF point (pt) = 1/72 inch; 1 inch = 25.4 mm.
export const MM_PER_PT = 25.4 / 72;
export const PT_PER_MM = 72 / 25.4;

// Sensible bounds for signature size — wide enough that the user can drag
// freely without zero-clamping, narrow enough that a stray drag doesn't
// produce a slot the size of the whole page.
export const MIN_WIDTH_MM = 8;
export const MAX_WIDTH_MM = 200;
export const DEFAULT_ASPECT_RATIO = 0.4;

export const ptToMm = (pt: number): number => pt * MM_PER_PT;
export const mmToPt = (mm: number): number => mm * PT_PER_MM;

export const clampWidthMm = (widthMm: number): number =>
  Math.min(MAX_WIDTH_MM, Math.max(MIN_WIDTH_MM, widthMm));

export const aspectRatioFromPx = (
  naturalWidthPx: number | null | undefined,
  naturalHeightPx: number | null | undefined,
): number => {
  if (
    !naturalWidthPx ||
    !naturalHeightPx ||
    naturalWidthPx <= 0 ||
    naturalHeightPx <= 0
  ) {
    return DEFAULT_ASPECT_RATIO;
  }
  return naturalHeightPx / naturalWidthPx;
};

/** Пропорция плашки открепленной ЭП: надпись в рамке, а не картинка. */
const CAPTION_ASPECT_RATIO = 0.55;

/** Высота рамки подписи на странице, мм: по пропорции картинки или плашки. */
export const signatureHeightMm = (
  widthMm: number,
  slotInfo:
    | {
        sign_mode?: string | null;
        natural_width_px?: number | null;
        natural_height_px?: number | null;
      }
    | undefined,
): number =>
  widthMm *
  (slotInfo?.sign_mode === "detached_text"
    ? CAPTION_ASPECT_RATIO
    : aspectRatioFromPx(
        slotInfo?.natural_width_px,
        slotInfo?.natural_height_px,
      ));
