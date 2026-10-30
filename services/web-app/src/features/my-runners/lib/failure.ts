import { useCallback } from "react";
import { useTranslation } from "react-i18next";

/**
 * Текст отказа по коду: сначала каталог ошибок сервера (errors:code.*), затем
 * сетевой сбой, иначе общий текст. Коды личных раннеров (personal_runner_limit,
 * runner_revoked, personal_runners_disabled...) уже есть в каталоге.
 */
export const useFailureText = (): ((code: string) => string) => {
  const { t, i18n } = useTranslation("runners");
  return useCallback(
    (code: string) => {
      if (code === "network") return t("failure.network");
      const key = `errors:code.${code}`;
      return i18n.exists(key) ? t(key) : t("failure.unknown");
    },
    [t, i18n],
  );
};
