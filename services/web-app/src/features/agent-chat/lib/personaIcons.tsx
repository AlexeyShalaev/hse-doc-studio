import {
  Bot,
  ClipboardList,
  FileCheck2,
  GraduationCap,
  School,
  Settings2,
  Sparkles,
  SquarePen,
  type LucideProps,
} from "lucide-react";

export const CUSTOM_PERSONA_ID = "custom";
export const DEFAULT_PERSONA_ID = "default";

type PersonaIconProps = { id: string; builtin?: boolean } & LucideProps;

// Renders the lucide icon for a backend persona id. A static module-level
// component (literal JSX per case) so the icon isn't a component created during
// render. User-defined roles (builtin === false) get a generic Sparkles; unknown
// built-in ids fall back to the neutral Bot.
export const PersonaIcon = ({
  id,
  builtin = true,
  ...props
}: PersonaIconProps) => {
  if (!builtin) {
    return <Sparkles {...props} />;
  }
  switch (id) {
    case "supervisor_critic":
      return <GraduationCap {...props} />;
    case "espd_proofreader":
      return <FileCheck2 {...props} />;
    case "latex_engineer":
      return <Settings2 {...props} />;
    case "methodologist":
      return <ClipboardList {...props} />;
    case "committee_member":
      return <School {...props} />;
    case CUSTOM_PERSONA_ID:
      return <SquarePen {...props} />;
    default:
      return <Bot {...props} />;
  }
};
