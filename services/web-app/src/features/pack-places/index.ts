export { PackPlacesEditor } from "./ui/PackPlacesEditor";
export type { PackPlacesEditorProps } from "./ui/PackPlacesEditor";
// Модель мест (чистые функции): новый экран «Содержимое, Подписи» строит свой редактор на ней.
export {
  bindingOf,
  dateMoveOpFrom,
  dateOpFrom,
  freeDateAnchors,
  marksBefore,
  placeOpFrom,
  placeholderHeightMm,
  placementOf,
  stamperStateOf,
} from "./lib/placesState";
export type { Binding, PlacesStamperState } from "./lib/placesState";
