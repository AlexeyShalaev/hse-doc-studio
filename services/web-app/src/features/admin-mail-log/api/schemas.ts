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
  "admin_resend",
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
  /** Запланирован автоповтор временного сбоя (14, V6). */
  next_attempt_at: iso.nullable(),
  /** Время последней попытки, если их больше одной. */
  last_attempt_at: iso.nullable(),
  /** Ручной повтор: исходная строка журнала (V2). */
  resent_from_id: z.number().int().nullable(),
});

/** Страница журнала: курсор непрозрачный, оценка числа только без фильтров. */
export const MailLogPageSchema = cursorPageOf(MailLogEntrySchema);

/** Письмо, перерисованное из сохранённых безопасных значений (L3). */
export const MailLogPreviewSchema = z.strictObject({
  subject: z.string(),
  html: z.string(),
  text: z.string(),
});

/**
 * Почему «Отправить ещё раз» недоступно (14.2): общие правила по строке и актуальность объекта.
 * Сервер может прислать и другой код: тогда показывается общий текст.
 */
export const MAIL_RESEND_BLOCKS = [
  "status",
  "token_link",
  "smtp_test",
  "template_gone",
  "retrying",
  "too_old",
  "already_resent",
  "smtp_off",
  "recipient_gone",
  "recipient_changed",
  "recipient_blocked",
  "project_gone",
  "invitation_done",
  "request_done",
  "transfer_done",
  "route_done",
  "object_gone",
] as const;
export type MailResendBlock = (typeof MAIL_RESEND_BLOCKS)[number];

export const MailLogResendStateSchema = z.strictObject({
  allowed: z.boolean(),
  blocked: z.string().nullable(),
});

/** Ручной повтор строки: новая строка журнала. */
export const MailLogResentSchema = z.strictObject({
  id: z.number().int(),
  at: iso,
  status: z.enum(MAIL_STATUSES),
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
  /** Можно ли «Отправить ещё раз» (14, V1..V5). */
  resend: MailLogResendStateSchema,
  /** Ручные повторы этой строки, новые первыми. */
  resent: z.array(MailLogResentSchema),
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
  /** Не ушло, но Студия повторит сама; `failed` без них (V13). */
  retrying: z.number().int(),
  last_failure: MailLogLastFailureSchema.nullable(),
  retention_days: z.number().int(),
});

/** Итог «Отправить ещё раз». */
export const MailLogResendResultSchema = z.strictObject({
  outcome: z.enum(["sent", "failed", "retrying", "blocked"]),
  blocked: z.string().nullable(),
  entry_id: z.number().int().nullable(),
  reason: z.string().nullable(),
});

/** Тело «Отправить неушедшие»: фильтры списка без итога и курсора, период как since и until. */
export const MailLogResendBatchRequestSchema = z.strictObject({
  template: z.array(z.string()),
  reason: z.string().nullable(),
  recipient_id: z.string().nullable(),
  recipient: z.string().nullable(),
  project_id: z.string().nullable(),
  since: iso.nullable(),
  until: iso.nullable(),
  q: z.string().nullable(),
  dry_run: z.boolean(),
});

/** Сколько писем уйдёт (или ушло в отправку) и сколько пропущено по причинам. */
export const MailLogResendBatchSchema = z.strictObject({
  planned: z.number().int(),
  skipped: z.record(z.string(), z.number().int()),
  started: z.boolean(),
  limit: z.number().int(),
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
export type MailLogResent = z.infer<typeof MailLogResentSchema>;
export type MailLogResendResult = z.infer<typeof MailLogResendResultSchema>;
export type MailLogResendBatchRequest = z.infer<
  typeof MailLogResendBatchRequestSchema
>;
export type MailLogResendBatch = z.infer<typeof MailLogResendBatchSchema>;

/**
 * Каталоги contracts/server/fixtures журнала писем -> схема (6.2); те же пары разложены в
 * CONTRACT_SCHEMAS. Копия эталонов для галерей и тестов: testing/serverFixtures.
 */
export const MAIL_LOG_CONTRACT_SCHEMAS: Record<string, ZodType> = {
  AdminMailLogEntry: MailLogEntrySchema,
  AdminMailLogPage: MailLogPageSchema,
  AdminMailLogDetail: MailLogDetailSchema,
  AdminMailLogSummary: MailLogSummarySchema,
  AdminMailLogResendResult: MailLogResendResultSchema,
  AdminMailLogResendBatch: MailLogResendBatchSchema,
  AdminMailLogResendBatchRequest: MailLogResendBatchRequestSchema,
};
