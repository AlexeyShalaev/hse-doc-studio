import {
  MAIL_FAILURES,
  MAIL_TEMPLATE_GROUPS,
  type MailFailure,
  type MailLogEntry,
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

/** Подсказка «Что можно сделать» по виду письма (4.2, L6); у удалённого вида её нет. */
export type MailNextKey =
  | "reset_password"
  | "verify_email"
  | "invite"
  | "email_change"
  | "project_invitation_link"
  | "inbox"
  | "notice"
  | "smtp_test";

const NEXT_BY_TEMPLATE: Partial<Record<string, MailNextKey>> = {
  reset_password: "reset_password",
  verify_email: "verify_email",
  invite: "invite",
  email_change: "email_change",
  project_invitation_link: "project_invitation_link",
  smtp_test: "smtp_test",
  // Письма о действии с аккаунтом: действие уже сделано, во «Входящие» они не идут.
  reset_notice: "notice",
  passkey_added: "notice",
  passkey_reset: "notice",
};

/** Подсказка по виду: письма со ссылкой, уведомления во «Входящих», письма о действии. */
export const mailNextKey = (template: string): MailNextKey | null => {
  const own = NEXT_BY_TEMPLATE[template];
  if (own) return own;
  const group = mailTemplateGroup(template);
  // Уведомления проектов и маршрута дублируют запись во «Входящих» (MAILED_KINDS).
  return group === "projects" || group === "signing" ? "inbox" : null;
};

/** Строка блока «Что можно сделать»: сначала про итог, затем по виду письма. */
export type MailNextStep =
  /** Сбой из-за настроек почты: «Сначала проверьте настройки почты» со ссылкой. */
  | { kind: "checkSmtp" }
  /** Почта не была настроена: письмо не уходило и само не уйдёт. */
  | { kind: "smtpOff" }
  /** Письмо не положено: это не сбой. */
  | { kind: "suppressed"; reason: string | null }
  | { kind: "template"; key: MailNextKey };

export const mailNextSteps = (entry: {
  template: string;
  status: MailLogEntry["status"];
  reason: string | null;
}): MailNextStep[] => {
  const steps: MailNextStep[] = [];
  if (entry.status === "failed" && isSmtpSettingsFailure(entry.reason)) {
    steps.push({ kind: "checkSmtp" });
  }
  if (entry.status === "not_sent") steps.push({ kind: "smtpOff" });
  if (entry.status === "suppressed") {
    steps.push({ kind: "suppressed", reason: entry.reason });
  }
  const key = mailNextKey(entry.template);
  if (key) steps.push({ kind: "template", key });
  return steps;
};

/** Длительность попытки: «420 мс» до секунды, дальше секунды с одним знаком. */
export const mailDuration = (
  ms: number,
): { unit: "ms" | "seconds"; value: number } =>
  ms < 1000
    ? { unit: "ms", value: Math.max(0, Math.round(ms)) }
    : { unit: "seconds", value: Math.round(ms / 100) / 10 };
