import { useTranslation } from "react-i18next";
import type { PackSubmissionWhen } from "@entities/pack-studio";

/** Условие словами: «если научный руководитель указан и из компании». */
export const useWhenText = () => {
  const { t } = useTranslation("packStudio");
  return (when: PackSubmissionWhen | null): string =>
    when === null
      ? t("submission.when.always")
      : t(`submission.when.${when.role ?? "any"}`, {
          person: t(`submission.person.${when.person}`),
        });
};
