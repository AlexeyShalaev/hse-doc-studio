import type { ZodType } from "zod";
import { z } from "zod";
import { cursorPageOf } from "@shared/api";

// Журнал писем в админке (docs/design/mail-log.md, раздел 6): зеркало api/schemas/mail_log.py.
// strictObject повторяет extra=forbid на стороне бэкенда: лишнее поле значит расхождение сторон.
// Все поля приходят явно, пустое значение null, время ISO 8601 UTC.

const iso = z.string().min(1);

/** Итог попытки (L2): ушло, не ушло, SMTP не настроен, письмо не положено. */
export const MAIL_STATUSES = [
  "sent",
  "failed",
  "not_sent",
  "suppressed",
] as const;
export type MailStatus = (typeof MAIL_STATUSES)[number];

/** Кто вызвал письмо (L8). */
export const MAIL_CAUSES = ["user", "anonymous", "system"] as const;
export type MailCause = (typeof MAIL_CAUSES)[number];

export const MAIL_LANGS = ["ru", "en"] as const;
export type MailLang = (typeof MAIL_LANGS)[number];

/**
 * Виды писем этой версии (`MailTemplate` в core/mail/compose.py). Строка журнала может нести
 * и неизвестный вид (удалён из Студии): поле `template` в схеме строка, а `template_known` false.
 */
export const MAIL_TEMPLATES = [
  "verify_email",
  "reset_password",
  "invite",
  "email_change",
  "reset_notice",
  "passkey_added",
  "passkey_reset",
  "project_invitation",
  "project_invitation_link",
  "access_request",
  "transfer_request",
  "signing_request",
  "signing_request_sign",
  "signing_request_new_version",
  "signing_reminder",
  "signing_skipped",
  "signing_returned",
  "signing_completed",
  "checkpoint_due",
  "smtp_test",
] as const;
export type MailTemplate = (typeof MAIL_TEMPLATES)[number];

/** Группы фильтра «Вид письма» (4.1). */
export const MAIL_TEMPLATE_GROUPS = {
  account: [
    "verify_email",
    "reset_password",
    "invite",
    "email_change",
    "reset_notice",
    "passkey_added",
    "passkey_reset",
  ],
  projects: [
    "project_invitation",
    "project_invitation_link",
    "access_request",
    "transfer_request",
    "checkpoint_due",
  ],
  signing: [
    "signing_request",
    "signing_request_sign",
    "signing_request_new_version",
    "signing_reminder",
    "signing_skipped",
    "signing_returned",
    "signing_completed",
  ],
  service: ["smtp_test"],
} as const satisfies Record<string, readonly MailTemplate[]>;
export type MailTemplateGroup = keyof typeof MAIL_TEMPLATE_GROUPS;

export const isKnownMailTemplate = (value: string): value is MailTemplate =>
  (MAIL_TEMPLATES as readonly string[]).includes(value);

/** Почему письмо не отправлялось (`not_sent` и `suppressed`). */
export const MAIL_SKIP_REASONS = [
  "smtp_off",
  "email_unverified",
  "account_blocked",
] as const;
export type MailSkipReason = (typeof MAIL_SKIP_REASONS)[number];

/** Класс сбоя у `failed` (L16). Неизвестный класс показывается как `other`. */
export const MAIL_FAILURES = [
  "auth",
  "connect",
  "timeout",
  "tls",
  "recipient_refused",
  "sender_refused",
  "data_refused",
  "disconnected",
  "smtp_off",
  "other",
] as const;
export type MailFailure = (typeof MAIL_FAILURES)[number];

/** Коды сценария (`origin`, L8), у которых есть подпись. Сервер может прислать и другой. */
export const MAIL_ORIGINS = [
  "register",
  "resend_verification",
  "forgot_password",
  "admin_invite",
  "admin_invite_resend",
  "email_change",
  "admin_reset_link",
  "passkey_added",
  "admin_passkeys_reset",
  "notification",
  "project_invite",
  "project_invite_resend",
  "signing_reinvite",
  "signing_auto_reminder",
  "smtp_test",
] as const;
export type MailOrigin = (typeof MAIL_ORIGINS)[number];

/**
 * Человек установки (`AdminPersonRef`): получатель или вызвавший. Само поле null, если адрес не
 * человека установки или он удалён; почты может не быть.
 */
export const MailLogPersonSchema = z.strictObject({
  id: z.string(),
  name: z.string(),
  email: z.string().nullable(),
});

/** Ответ SMTP у `failed`: код и очищенный текст до 300 символов. */
export const MailLogFailureSchema = z.strictObject({
  smtp_code: z.number().int().nullable(),
  text: z.string().nullable(),
});

/** Проект письма (на сервере UUID строкой); name null, если проекта уже нет. */
export const MailLogProjectSchema = z.strictObject({
  id: z.string(),
  name: z.string().nullable(),
});

/** Объект письма (L9): `signing_route`, `project_invitation`, `registration_invite` и т. д. */
export const MailLogRefSchema = z.strictObject({
  kind: z.string(),
  id: z.string(),
});

export const MailLogEntrySchema = z.strictObject({
  id: z.number().int(),
  at: iso,
  template: z.string(),
  template_known: z.boolean(),
  lang: z.enum(MAIL_LANGS),
  to_email: z.string(),
  to_user: MailLogPersonSchema.nullable(),
  subject: z.string(),
  status: z.enum(MAIL_STATUSES),
  reason: z.string().nullable(),
  failure: MailLogFailureSchema.nullable(),
  message_id: z.string().nullable(),
  attempts: z.number().int(),
  duration_ms: z.number().int(),
  cause: z.enum(MAIL_CAUSES),
  actor: MailLogPersonSchema.nullable(),
  task: z.string().nullable(),
  origin: z.string(),
  project: MailLogProjectSchema.nullable(),
  ref: MailLogRefSchema.nullable(),
});

/** Страница журнала: курсор непрозрачный, оценка числа только без фильтров. */
export const MailLogPageSchema = cursorPageOf(MailLogEntrySchema);

/** Письмо, перерисованное из сохранённых безопасных значений (L3). */
export const MailLogPreviewSchema = z.strictObject({
  subject: z.string(),
  html: z.string(),
  text: z.string(),
});

export const MailLogDetailSchema = z.strictObject({
  entry: MailLogEntrySchema,
  /** null, если вида письма в этой версии нет. */
  preview: MailLogPreviewSchema.nullable(),
  /** В письме была ссылка с токеном: в журнале её нет. */
  link_hidden: z.boolean(),
  /** В письме было сообщение человека: в журнале только его длина. */
  note_hidden: z.boolean(),
  /** Шаблон менялся с момента отправки (L5). */
  rerendered: z.boolean(),
});

export const MailLogLastFailureSchema = z.strictObject({
  at: iso,
  reason: z.string(),
});

/** Полоса за сутки, счётчик меню и плашка «Почта не настроена» (L14). */
export const MailLogSummarySchema = z.strictObject({
  smtp_configured: z.boolean(),
  window_hours: z.literal(24),
  sent: z.number().int(),
  failed: z.number().int(),
  not_sent: z.number().int(),
  suppressed: z.number().int(),
  last_failure: MailLogLastFailureSchema.nullable(),
  retention_days: z.number().int(),
});

export type MailLogPerson = z.infer<typeof MailLogPersonSchema>;
export type MailLogFailure = z.infer<typeof MailLogFailureSchema>;
export type MailLogProject = z.infer<typeof MailLogProjectSchema>;
export type MailLogRef = z.infer<typeof MailLogRefSchema>;
export type MailLogEntry = z.infer<typeof MailLogEntrySchema>;
export type MailLogPage = z.infer<typeof MailLogPageSchema>;
export type MailLogPreview = z.infer<typeof MailLogPreviewSchema>;
export type MailLogDetail = z.infer<typeof MailLogDetailSchema>;
export type MailLogSummary = z.infer<typeof MailLogSummarySchema>;

/**
 * Каталоги contracts/server/fixtures журнала писем -> схема (6.2); те же пары разложены в
 * CONTRACT_SCHEMAS. Копия эталонов для галерей и тестов: testing/serverFixtures.
 */
export const MAIL_LOG_CONTRACT_SCHEMAS: Record<string, ZodType> = {
  AdminMailLogEntry: MailLogEntrySchema,
  AdminMailLogPage: MailLogPageSchema,
  AdminMailLogDetail: MailLogDetailSchema,
  AdminMailLogSummary: MailLogSummarySchema,
};
