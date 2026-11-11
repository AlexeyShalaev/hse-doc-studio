import {
  MAIL_FAILURES,
  MAIL_TEMPLATE_GROUPS,
  type MailFailure,
  type MailLogSummary,
  type MailTemplateGroup,
} from "../api/schemas";

// Правила журнала писем, общие для списка (W2) и карточки (W3): docs/design/mail-log.md, 4.1 и 4.2.

/** Группа вида письма в фильтре; null у вида, которого в этой версии нет. */
export const mailTemplateGroup = (
  template: string,
): MailTemplateGroup | null => {
  for (const [group, templates] of Object.entries(MAIL_TEMPLATE_GROUPS)) {
    if ((templates as readonly string[]).includes(template)) {
      return group as MailTemplateGroup;
    }
  }
  return null;
};

/** «Не отправлялось» в полосе за сутки: `not_sent` и `suppressed` вместе. */
export const skippedCount = (summary: MailLogSummary): number =>
  summary.not_sent + summary.suppressed;

/** Класс сбоя строки; неизвестный сервером класс показывается как `other`. */
export const mailFailureOf = (reason: string | null): MailFailure =>
  reason !== null && (MAIL_FAILURES as readonly string[]).includes(reason)
    ? (reason as MailFailure)
    : "other";

/** Подсказка под полосой за сутки: какой блок настроек проверить. */
export type MailHint = "auth" | "connect" | "tls";

/**
 * Подсказка по последнему сбою (4.1): вход на SMTP, соединение (`connect` и `timeout`) или
 * защищённое соединение. У остальных классов подсказки нет: они про адрес или письмо.
 */
export const mailHintOf = (summary: MailLogSummary): MailHint | null => {
  const reason = summary.last_failure?.reason ?? null;
  if (reason === "auth" || reason === "tls") return reason;
  if (reason === "connect" || reason === "timeout") return "connect";
  return null;
};

/** Сбой из-за настроек почты, а не адреса: в карточке ссылка «Сначала проверьте настройки почты». */
export const isSmtpSettingsFailure = (reason: string | null): boolean =>
  reason === "auth" ||
  reason === "connect" ||
  reason === "timeout" ||
  reason === "tls";

/** Номер письма из `?mail=<id>`; мусор в адресе не открывает карточку. */
export const parseMailId = (raw: string | null): number | null => {
  if (raw === null || !/^\d{1,15}$/.test(raw)) return null;
  const id = Number(raw);
  return id > 0 ? id : null;
};
