import { useStoredFlag } from "./panels";
import type { SectionId } from "../ui/sections/SectionShell";

/** Свёрнутость раздела: нужна и оболочке, и разделу, который грузит данные только раскрытым. */
export type SectionCollapse = readonly [boolean, (next: boolean) => void];

/** Запоминаемая свёрнутость раздела; `defaultCollapsed` действует, пока автор не выбрал сам. */
export const useSectionCollapse = (
  id: SectionId,
  defaultCollapsed = false,
): SectionCollapse =>
  useStoredFlag(`hse-studio.packOutcome.section.${id}`, defaultCollapsed);
