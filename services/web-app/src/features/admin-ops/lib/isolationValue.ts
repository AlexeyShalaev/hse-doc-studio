import { useTranslation } from "react-i18next";

/** Текст значения или «нет данных». */
export const useValue = () => {
  const { t } = useTranslation("adminRunnerIsolation");
  return {
    text: (value: string | number | null | undefined): string =>
      value === null || value === undefined || value === ""
        ? t("value.none")
        : String(value),
    flag: (value: boolean | null | undefined): string =>
      value === null || value === undefined
        ? t("value.none")
        : value
          ? t("value.yes")
          : t("value.no"),
  };
};
