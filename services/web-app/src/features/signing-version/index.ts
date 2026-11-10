// Версия на подписи (docs/design/signing-route.md, 12, срез W11): вкладка «Подписи» документа и
// предупреждения пакета о документах, изменённых после отправки на подпись.
export { SignedVersionPanel } from "./ui/SignedVersionPanel";
export type { SignedVersionPanelProps } from "./ui/SignedVersionPanel";
export {
  PackVersionPreflight,
  PackVersionWarnings,
} from "./ui/PackVersionNotes";
export type {
  PackVersionPreflightProps,
  PackVersionWarningsProps,
} from "./ui/PackVersionNotes";
export { useNewVersionLink } from "./model/useNewVersionLink";
export { formatVersionAt, shortSha } from "./lib/versionDate";
