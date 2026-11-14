import { useCallback } from "react";
import { useTranslation } from "react-i18next";
import {
  MAIL_FAILURES,
  MAIL_RESEND_BLOCKS,
  MAIL_SKIP_REASONS,
  isKnownMailTemplate,
  type MailLogEntry,
  type MailStatus,
} from "../api/schemas";
import { isMailRetrying } from "../lib/mailLog";

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

/** Метка итога строки: «Повтор» (жёлтая), пока Студия ещё повторит отправку сама (V13). */
export const statusBadgeOf = (
  entry: Pick<MailLogEntry, "status" | "next_attempt_at">,
): {
  variant: "success" | "error" | "default" | "subtle" | "warning";
  key: string;
} =>
  isMailRetrying(entry)
    ? { variant: "warning", key: "status.retrying" }
    : { variant: STATUS_BADGE[entry.status], key: `status.${entry.status}` };

/** Почему письмо нельзя отправить ещё раз (14.2); незнакомый код общим текстом. */
export const useBlockedText = () => {
  const { t } = useTranslation("adminMail");
  return useCallback(
    (code: string, limit = 200): string =>
      (MAIL_RESEND_BLOCKS as readonly string[]).includes(code) ||
      code === "over_limit"
        ? t(`resend.blocked.${code}`, { limit })
        : t("resend.blocked.unknown", { code }),
    [t],
  );
};
