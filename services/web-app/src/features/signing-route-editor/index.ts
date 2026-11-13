// «Отправка на подписание» (docs/design/signing-route.md, 3.1). Наружу только ленивая обёртка:
// сам экран уходит в свой чанк.
export { SigningRouteEditorLazy as SigningRouteEditor } from "./ui/SigningRouteEditorLazy";
export type { SigningRouteEditorProps } from "./ui/SigningRouteEditor";
// Шапка «Маршрут из шаблона» и окно «Вернуть как в шаблоне?» для галереи разработчика (15.7).
export { RestorePresetDialog, RoutePresetBar } from "./ui/RoutePresetBar";
export type {
  RestorePresetDialogProps,
  RoutePresetBarProps,
} from "./ui/RoutePresetBar";
