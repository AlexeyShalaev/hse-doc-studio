// Новый интерфейс Студии шаблонов (docs/design/pack-studio-ux.md, раздел 12 «Как подключаться
// к каркасу»). Публичное для страниц и срезов; записи галереи (`gallery.ts`) сюда не входят:
// их подключает только dev-маршрут.
export {
  SpaceProvider,
  parseSelection,
  useSpace,
} from "./context/SpaceContext";
export type {
  SpaceLocation,
  SpaceProviderProps,
  SpaceValue,
} from "./context/SpaceContext";
export { buildSpaceUrl } from "./context/nav";
export type { SpaceHere, SpaceNavPatch } from "./context/nav";
export { useSpaceNav } from "./context/useSpaceNav";
export type { SpaceNav } from "./context/useSpaceNav";
export { useSituation } from "./context/useSituation";
export type { SituationControls } from "./context/useSituation";
export { readSituation, writeInputs } from "./context/situation";
export type { Situation } from "./context/situation";
export {
  readPlace,
  readUi,
  useRememberPlace,
  writePlace,
  writeUi,
} from "./context/memory";
export type { SpacePlace } from "./context/memory";
export { hasVersion, resolveEntryPlace } from "./context/entry";
export type { EntryHints, EntryPlace } from "./context/entry";
export { NO_CHANGES } from "./changes/types";
export type { ChangesRequest, ChangesStatus } from "./changes/types";
export { useChangesStatus } from "./changes/useChangesStatus";
export { SpaceShell } from "./shell/SpaceShell";
export type { SpaceShellProps } from "./shell/SpaceShell";
export { SpaceScreen } from "./shell/SpaceScreen";
export { SpaceTabs } from "./shell/DefaultParts";
export { defineSpaceSlots, mergeSpaceSlots } from "./shell/spaceSlots";
export type { SpaceSlots, SpaceTabSlot } from "./shell/spaceSlots";
