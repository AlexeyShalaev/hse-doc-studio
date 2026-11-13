// Сроки контрольных точек (docs/design/signing-route.md, раздел 16, срез W16): строка срока на
// точке, пометка в списке проектов и срок точки в редакторе маршрута.
export { CheckpointDeadlineLine } from "./ui/CheckpointDeadlineLine";
export type {
  CheckpointDeadlineLineProps,
  CheckpointDeadlineProfile,
} from "./ui/CheckpointDeadlineLine";
export { DeadlineForm } from "./ui/DeadlineForm";
export { NextDeadlineChip } from "./ui/NextDeadlineChip";
export { RoutePointDeadline } from "./ui/RoutePointDeadline";
export {
  DEADLINE_TONE,
  TONE_COLOR,
  useDeadlineText,
} from "./lib/useDeadlineText";
export type { DeadlineTone, PointDeadline } from "./lib/useDeadlineText";
export {
  dismissDeadlinePrompt,
  isDeadlinePromptDismissed,
} from "./model/dismissed";
