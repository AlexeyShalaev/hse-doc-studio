export { VersionBar } from "./ui/VersionBar";
export type { VersionBarProps } from "./ui/VersionBar";
export { NewVersionDialog } from "./ui/NewVersionDialog";
export type {
  NewVersionDialogProps,
  NewVersionTarget,
} from "./ui/NewVersionDialog";
// Для раздела отправки в панели «Изменения» нового интерфейса (features/pack-space/next-step):
// чистые правила номера и заметок переиспользуются как есть.
export {
  UPDATE_CLASSES,
  currentClass,
  isSofter,
  linesOf,
  needsNote,
  notesOf,
  notesParallel,
} from "./lib/versionWizard";
