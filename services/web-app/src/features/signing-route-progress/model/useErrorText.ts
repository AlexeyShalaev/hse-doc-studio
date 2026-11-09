import { useCallback } from "react";
import { useTranslation } from "react-i18next";
import { ApiError, failureCode } from "@shared/api";

const KNOWN = new Set([
  "doc_changed",
  "invalid_transition",
  "participant_not_waiting",
  "network",
]);

/** Текст отказа действия с маршрутом по коду из тела ответа (раздел 8.1). */
export const useErrorText = (): ((error: unknown) => string) => {
  const { t } = useTranslation("signingProgress");
  return useCallback(
    (error: unknown) => {
      const code = failureCode(error);
      if (code === "rate_limited" && error instanceof ApiError) {
        const seconds = Number(error.data?.retry_after ?? 60);
        return t("error.rate_limited", {
          minutes: Math.max(1, Math.ceil(seconds / 60)),
        });
      }
      if (KNOWN.has(code)) return t(`error.${code}`);
      return error instanceof ApiError && error.detail !== ""
        ? error.detail
        : t("error.generic");
    },
    [t],
  );
};
