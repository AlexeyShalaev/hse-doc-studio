// Журнал писем в админке (docs/design/mail-log.md). Срез W1: схемы, API и запросы; W2: раздел
// «Письма» со списком; карточку письма (ui/MailLogCard) делает W3. Состояния галереи и моки:
// ./testing.
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
export { mailWhen } from "./lib/when";
export type { MailWhen } from "./lib/when";
export { ensureAdminMailLocales } from "./lib/locales";
export { MAIL_PARAM, MailLog } from "./ui/MailLog";
export { MailLogCard } from "./ui/MailLogCard";
export type { MailLogCardProps } from "./ui/MailLogCard";
export { MailDayBand, MailLogView, SMTP_SETTINGS_PATH } from "./ui/MailLogView";
export type { MailLogViewProps } from "./ui/MailLogView";
export { getAdminMailLogGallery } from "./ui/mailLogGallery";
