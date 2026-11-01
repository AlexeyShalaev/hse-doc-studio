import { useMemo } from "react";
import { useTranslation } from "react-i18next";
import { useProject } from "@entities/project";

export const SUPERVISOR_PERSONAS = [
  "supervisor",
  "co_supervisor",
  "academic_supervisor",
] as const;

export type PersonaOption = { value: string; label: string };

/** Варианты привязки: «Без привязки», авторы проекта по слагу и роли руководителей. */
export const usePersonaOptions = (projectId: string): PersonaOption[] => {
  const { t } = useTranslation("invitations");
  const project = useProject(projectId);
  const authors = project.data?.authors;
  return useMemo(
    () => [
      { value: "", label: t("persona.none") },
      ...(authors ?? []).flatMap((a) =>
        a.slug ? [{ value: a.slug, label: a.name || a.slug }] : [],
      ),
      ...SUPERVISOR_PERSONAS.map((p) => ({
        value: p,
        label: t(`persona.${p}`),
      })),
    ],
    [authors, t],
  );
};
