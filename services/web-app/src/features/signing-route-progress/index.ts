// Ход маршрута подписания у автора (docs/design/signing-route.md, 3.1, срез W3): карточка
// «Подписание» на точке сдачи и плашка в редакторе документа, который держит идущий маршрут.
export { SigningRouteCard } from "./ui/SigningRouteCard";
export type { SigningRouteCardProps } from "./ui/SigningRouteCard";
export { SigningHoldBanner } from "./ui/SigningHoldBanner";
export type { SigningHoldBannerProps } from "./ui/SigningHoldBanner";
export {
  useDocRouteVersion,
  useDocSigningHold,
} from "./model/useDocSigningHold";
export type { DocRouteVersion, SigningHold } from "./model/useDocSigningHold";
export { NewVersionAction } from "./ui/NewVersionAction";
export type { NewVersionActionProps } from "./ui/NewVersionAction";
export { RouteWaitNote } from "./ui/RouteWaitNote";
export type { RouteWaitNoteProps } from "./ui/RouteWaitNote";
export { displayName, useWaitText } from "./lib/useWaitText";
export { usePersonaLabel } from "./lib/usePersonaLabel";
export { useRouteSlotHints } from "./model/useRouteSlotHints";
export { routeTally } from "./lib/routeView";
export type { RouteTally } from "./lib/routeView";
export { usePackGate } from "./model/usePackGate";
export type {
  PackGate,
  PackGateRow,
  UsePackGateArgs,
} from "./model/usePackGate";
