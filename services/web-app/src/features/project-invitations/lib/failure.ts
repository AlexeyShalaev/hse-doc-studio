import { useCallback } from "react";
import { useTranslation } from "react-i18next";

/** Текст отказа по коду: каталог ошибок сервера (errors:code.*), иначе общий текст трека. */
export const useFailureText = (): ((code: string) => string) => {
  const { t, i18n } = useTranslation("invitations");
  return useCallback(
    (code: string) => {
      if (code === "network") return t("failure.network");
      const key = `errors:code.${code}`;
      return i18n.exists(key) ? t(key) : t("failure.unknown");
    },
    [t, i18n],
  );
};
