import { useCallback } from "react";
import { useTranslation } from "react-i18next";
import type { ProjectRole } from "@entities/session";

/** Роли от слабой к сильной: порядок нужен фильтрам и подсказкам. */
export const PROJECT_ROLES: readonly ProjectRole[] = [
  "reader",
  "reviewer",
  "editor",
  "owner",
];

/**
 * Названия ролей на проекте (Читатель, Рецензент, Редактор, Владелец): один
 * словарь для карточек, тостов отказа и будущих экранов доступа. Термины те же,
 * что в core/access на бэкенде.
 */
export const useProjectRoleLabel = (): ((role: ProjectRole) => string) => {
  const { t } = useTranslation("projectAccess");
  return useCallback((role: ProjectRole) => t(`roles.${role}`), [t]);
};
