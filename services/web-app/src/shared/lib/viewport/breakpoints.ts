// Брейкпоинты адаптива. Единственное место, где записаны границы: CSS-медиазапросы
// в index.css повторяют те же числа (docs/design/mobile-layout.md).
//
//   телефон   до 767.98 px     нижняя панель вкладок, шторки вместо окон, карточки вместо таблиц
//   планшет   768 – 1023.98 px рейка и панели как на десктопе, но уже и с крупными зонами касания
//   десктоп   от 1024 px       как было

export const PHONE_MAX_WIDTH = 767.98;
export const TABLET_MAX_WIDTH = 1023.98;

export const PHONE_QUERY = `(max-width: ${String(PHONE_MAX_WIDTH)}px)`;
export const TABLET_QUERY = `(min-width: 768px) and (max-width: ${String(TABLET_MAX_WIDTH)}px)`;
/** Телефон или планшет: всё, что уже десктопа. */
export const COMPACT_QUERY = `(max-width: ${String(TABLET_MAX_WIDTH)}px)`;
/** Основной указатель грубый (палец): зоны касания крупнее, наведения нет. */
export const COARSE_POINTER_QUERY = "(pointer: coarse)";

export type ViewportClass = "phone" | "tablet" | "desktop";
