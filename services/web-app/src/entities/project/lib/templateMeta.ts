import type { z } from "zod";
import * as Icons from "lucide-react";
import { GraduationCap, type LucideIcon } from "lucide-react";
import { useTranslation } from "react-i18next";
import { usePacks } from "@entities/template-catalog";
import { pickLocalized } from "@shared/lib";
import type { ProjectResponseSchema } from "../api/projectSchemas";

type Project = z.infer<typeof ProjectResponseSchema>;

export type TemplateMeta = {
  label: string;
  icon: LucideIcon;
  accentHue: number;
};

const resolveIcon = (name: string | undefined): LucideIcon => {
  if (!name) return GraduationCap;
  const candidate = (
    Icons as unknown as Record<string, LucideIcon | undefined>
  )[name];
  return candidate ?? GraduationCap;
};

const FALLBACK_ICON = GraduationCap;
const FALLBACK_HUE = 230;

/**
 * Resolves localized template label + icon + accent hue from the backend
 * catalog (`/catalog/packs`). Uses the project's locked `pack_id` and
 * `template_id` to look up the entry. Falls back to a generic value while
 * catalog data is loading, or if the pack/template can't be resolved (e.g.
 * project locked to a pack that's no longer installed).
 */
export const useTemplateMeta = (
  project: Project | null | undefined,
): TemplateMeta => {
  const { data: packs } = usePacks();
  const { t, i18n } = useTranslation("documents");

  const fallback: TemplateMeta = {
    label: t("template.fallbackLabel"),
    icon: FALLBACK_ICON,
    accentHue: FALLBACK_HUE,
  };

  if (!project || !packs) return fallback;

  const pack = packs.find((p) => p.id === project.lock.pack_id);
  const template = pack?.templates.find(
    (tpl) => tpl.id === project.lock.template_id,
  );
  if (!template) return fallback;

  const label = pickLocalized(template.name, i18n.language, template.id);

  return {
    label,
    icon: resolveIcon(template.icon),
    accentHue: template.accent_hue,
  };
};
