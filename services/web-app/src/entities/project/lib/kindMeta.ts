import { Microscope, Wrench, type LucideIcon } from "lucide-react";
import { useTranslation } from "react-i18next";

export type KindMeta = {
  label: string;
  icon: LucideIcon;
  hue: number;
  chroma: number;
};

/**
 * Localized label + icon + accent for a project's kind (research vs applied),
 * so the type is visible at a glance next to the template icon (project cards,
 * rail). Research gets a vivid violet + microscope so it stands out; applied is
 * a muted slate + wrench (the "default" engineering track).
 */
export const useKindMeta = (kind: string | null | undefined): KindMeta => {
  const { t } = useTranslation("documents");
  if (kind === "research") {
    return {
      label: t("kind.research"),
      icon: Microscope,
      hue: 300,
      chroma: 0.15,
    };
  }
  return { label: t("kind.applied"), icon: Wrench, hue: 250, chroma: 0.05 };
};
