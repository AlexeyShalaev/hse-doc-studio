// Ход маршрута подписания у автора (docs/design/signing-route.md, 3.1, срез W3): карточка
// «Подписание» на точке сдачи и плашка в редакторе документа, который держит идущий маршрут.
export { SigningRouteCard } from "./ui/SigningRouteCard";
export type { SigningRouteCardProps } from "./ui/SigningRouteCard";
export { SigningHoldBanner } from "./ui/SigningHoldBanner";
export type { SigningHoldBannerProps } from "./ui/SigningHoldBanner";
export { useDocSigningHold } from "./model/useDocSigningHold";
export type { SigningHold } from "./model/useDocSigningHold";
