import { useCallback } from "react";
import { useTranslation } from "react-i18next";
import {
  MAIL_FAILURES,
  MAIL_SKIP_REASONS,
  isKnownMailTemplate,
  type MailStatus,
} from "../api/schemas";

// Подписи журнала писем, общие для списка (W2) и карточки (W3).

/** Цвет метки итога: зелёная, красная, серая. */
export const STATUS_BADGE: Record<
  MailStatus,
  "success" | "error" | "default" | "subtle"
> = {
  sent: "success",
  failed: "error",
  not_sent: "default",
  suppressed: "default",
};

/** Подпись вида письма из подписей образцов в «Вход и регистрация». */
export const useTemplateLabel = () => {
  const { t } = useTranslation("adminMail");
  const { t: ts } = useTranslation("adminSettings");
  return useCallback(
    (template: string): string =>
      isKnownMailTemplate(template)
        ? ts(`mailPreview.names.${template}`)
        : t("templateGone", { template }),
    [t, ts],
  );
};

/**
 * Причина словами: пропуск («почта не настроена») или класс сбоя («SMTP-сервер отклонил логин
 * или пароль»); незнакомое значение как есть.
 */
export const useReasonText = () => {
  const { t } = useTranslation("adminMail");
  return useCallback(
    (reason: string): string =>
      (MAIL_SKIP_REASONS as readonly string[]).includes(reason)
        ? t(`reason.${reason}`)
        : (MAIL_FAILURES as readonly string[]).includes(reason)
          ? t(`failure.${reason}`)
          : reason,
    [t],
  );
};
