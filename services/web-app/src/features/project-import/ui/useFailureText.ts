import { useTranslation } from "react-i18next";
import type { ImportFailure } from "../model/useProjectImport";

// Текст отказа: перевод по коду сервера, иначе его собственное сообщение, иначе общий текст.
export const useFailureText = (): ((failure: ImportFailure) => string) => {
  const { t, i18n } = useTranslation("projectImport");
  return (failure) => {
    const key = `errors:code.${failure.code}`;
    if (i18n.exists(key)) return t(key);
    return failure.detail !== "" ? failure.detail : t("failure.generic");
  };
};
