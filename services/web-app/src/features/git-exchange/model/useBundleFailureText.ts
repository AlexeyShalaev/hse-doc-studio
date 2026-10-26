import { useTranslation } from "react-i18next";
import { gitErrorMessage } from "@entities/git-sync";
import { HAS_OWN_COPY, type BundleFailure } from "./bundleFailure";

export type BundleFailureText = { message: string; hint: string | null };

// Слова отказа: для файла у окна свои формулировки («файл от другого проекта»),
// для остального берётся общий перевод кода или то, что прислал сервер.
export const useBundleFailureText = (): ((
  failure: BundleFailure,
) => BundleFailureText) => {
  const { t } = useTranslation("gitExchange");
  return (failure) => {
    if (HAS_OWN_COPY.has(failure.code)) {
      return {
        message: t(`failure.${failure.code}.text`),
        hint: t(`failure.${failure.code}.hint`),
      };
    }
    return {
      message: gitErrorMessage(failure.code, failure.detail, failure.params),
      hint: null,
    };
  };
};
