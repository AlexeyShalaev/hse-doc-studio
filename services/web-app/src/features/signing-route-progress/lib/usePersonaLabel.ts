import { useCallback } from "react";
import { useTranslation } from "react-i18next";

const SUPERVISORS = new Set([
  "supervisor",
  "co_supervisor",
  "academic_supervisor",
]);

/**
 * Роль человека строчными: «автор», «научный руководитель». У автора команды персона это
 * его слаг, а имя и так стоит в строке: роли нет (null).
 */
export const usePersonaLabel = (): ((persona: string) => string | null) => {
  const { t, i18n } = useTranslation("signingProgress");
  return useCallback(
    (persona: string) => {
      if (persona === "author") return t("persona.author");
      if (!SUPERVISORS.has(persona)) return null;
      const label = t(`invitations:persona.${persona}`);
      return label.charAt(0).toLocaleLowerCase(i18n.language) + label.slice(1);
    },
    [t, i18n.language],
  );
};
