// Журнал писем в админке (docs/design/mail-log.md). Срез W1: схемы, API и запросы; экраны
// списка и карточки добавляют W2 и W3. Состояния галереи и моки: ./testing.
export {
  MAIL_CAUSES,
  MAIL_FAILURES,
  MAIL_LANGS,
  MAIL_LOG_CONTRACT_SCHEMAS,
  MAIL_ORIGINS,
  MAIL_SKIP_REASONS,
  MAIL_STATUSES,
  MAIL_TEMPLATE_GROUPS,
  MAIL_TEMPLATES,
  MailLogDetailSchema,
  MailLogEntrySchema,
  MailLogPageSchema,
  MailLogSummarySchema,
  isKnownMailTemplate,
} from "./api/schemas";
export type {
  MailCause,
  MailFailure,
  MailLang,
  MailLogDetail,
  MailLogEntry,
  MailLogFailure,
  MailLogPage,
  MailLogPerson,
  MailLogPreview,
  MailLogProject,
  MailLogRef,
  MailLogSummary,
  MailOrigin,
  MailSkipReason,
  MailStatus,
  MailTemplate,
  MailTemplateGroup,
} from "./api/schemas";
export { mailLogApi } from "./api/mailLogApi";
export {
  MAIL_LOG_LIST,
  MAIL_LOG_SUMMARY_POLL_MS,
  isMailLogNotFound,
  mailLogKeys,
  useMailLog,
  useMailLogEntry,
  useMailLogSummary,
} from "./api/mailLogQueries";
export type { MailLogFilterName, MailLogListState } from "./api/mailLogQueries";
export {
  isSmtpSettingsFailure,
  mailFailureOf,
  mailHintOf,
  mailTemplateGroup,
  parseMailId,
  skippedCount,
} from "./lib/mailLog";
export type { MailHint } from "./lib/mailLog";
