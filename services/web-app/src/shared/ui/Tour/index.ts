// Тур с подсветкой. Не реэкспортируется из @shared/ui: его грузит только ленивый
// чанк онбординга, и в основной бандл он попадать не должен.
export { TourOverlay } from "./TourOverlay";
export type { TourOverlayLabels, TourOverlayProps } from "./TourOverlay";
export { placePopover, spotlightRect, SHEET_BELOW } from "./placement";
export type { Placement, PopoverBox, Rect, Viewport } from "./placement";
