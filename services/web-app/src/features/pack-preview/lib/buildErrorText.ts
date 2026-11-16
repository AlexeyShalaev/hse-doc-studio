import { useTranslation } from "react-i18next";

/** Текст неудачной сборки: свой для кодов предпросмотра, затем общий словарь ошибок. */
export const useBuildErrorText = () => {
  const { t, i18n } = useTranslation("packStudio");
  return (code: string): string => {
    if (i18n.exists(`packStudio:preview.error.${code}`)) {
      return t(`preview.error.${code}`);
    }
    if (i18n.exists(`errors:code.${code}`)) return t(`errors:code.${code}`);
    return t("preview.error.generic", { code });
  };
};
