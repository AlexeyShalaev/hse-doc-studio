import type {
  AdminRegistrationSettings,
  AdminSmtpSettings,
  RegistrationMode,
} from "@entities/session";
import type { SmtpDraft } from "./validate";

// Черновики форм настроек входа: что видит человек до сохранения.

export type RegistrationDraft = {
  mode: RegistrationMode;
  domains: string;
  approval: boolean;
};

export const registrationDraftOf = (
  settings: AdminRegistrationSettings,
): RegistrationDraft => ({
  mode: settings.registration_mode,
  domains: settings.registration_domains.join(", "),
  approval: settings.require_approval,
});

export const SMTP_KEYS = [
  "host",
  "port",
  "security",
  "username",
  "password",
  "from_address",
  "from_name",
] as const satisfies readonly (keyof SmtpDraft)[];

export const smtpDraftOf = (settings: AdminSmtpSettings): SmtpDraft => ({
  host: settings.host ?? "",
  port: String(settings.port),
  security: settings.security,
  username: settings.username ?? "",
  // Пароль сервер не отдаёт: поле пустое, пока человек не введёт новый.
  password: "",
  from_address: settings.from_address,
  from_name: settings.from_name,
});
