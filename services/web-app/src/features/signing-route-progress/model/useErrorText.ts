import { useCallback } from "react";
import { useTranslation } from "react-i18next";
import { ApiError, failureCode } from "@shared/api";

const KNOWN = new Set([
  "link_by_mail",
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
      if (code === "participant_not_skippable") {
        // Причина отказа пропуска (13.6) приходит рядом: не его очередь, обязательные подписи...
        const reason = error instanceof ApiError ? error.data?.reason : null;
        return typeof reason === "string" &&
          ["not_turn", "required_slots", "no_slots", "done"].includes(reason)
          ? t(`skip.blocked.${reason}`)
          : t("error.generic");
      }
      if (KNOWN.has(code)) return t(`error.${code}`);
      return error instanceof ApiError && error.detail !== ""
        ? error.detail
        : t("error.generic");
    },
    [t],
  );
};
