import {
  Bot,
  ClipboardCheck,
  ClipboardList,
  FileText,
  type LucideIcon,
  PenTool,
} from "lucide-react";

// Maps a pack-declared `icon` hint (FormDefinition.icon) to a concrete icon.
// Keeps icon choice data-driven per form — no special-casing of any form type.
const FORM_ICONS: Record<string, LucideIcon> = {
  bot: Bot,
  clipboard: ClipboardList,
  "clipboard-check": ClipboardCheck,
  file: FileText,
  pen: PenTool,
};

export const getFormIcon = (name?: string | null): LucideIcon =>
  (name ? FORM_ICONS[name] : undefined) ?? ClipboardList;
