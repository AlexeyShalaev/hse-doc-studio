import { useState, type ReactNode } from "react";
import { useTranslation } from "react-i18next";
import { useDraft } from "@shared/lib/useDraft";
import { StickySaveBar } from "@shared/ui";
import type {
  AdminAuthSettings,
  AdminRegistrationSettings,
  AdminSmtpSettings,
  UpdateAdminRegistrationRequest,
  UpdateAdminSmtpRequest,
} from "@entities/session";
import { failureKey } from "../lib/failure";
import { isLocked } from "../lib/locked";
import { settleSaves } from "../lib/saveAll";
import {
  invalidDomains,
  parseDomains,
  validateSmtp,
  type SmtpDraft,
  type SmtpIssues,
} from "../lib/validate";
import {
  registrationDraftOf,
  smtpDraftOf,
  type RegistrationDraft,
} from "../lib/drafts";
import { RegistrationSection } from "./RegistrationSection";
import { SignInSection, type SignInDraft } from "./SignInSection";
import { SmtpSection, type SmtpTest } from "./SmtpSection";

const REGISTRATION_FIELD: Record<keyof RegistrationDraft, string> = {
  mode: "auth.registration_mode",
  domains: "auth.registration_domains",
  approval: "auth.require_approval",
};

export type AuthSettingsFormProps = {
  registration: AdminRegistrationSettings;
  auth: AdminAuthSettings;
  smtp: AdminSmtpSettings;
  /** Провайдеры единого входа: свой раздел, правки в нём применяются сразу. */
  oidc: ReactNode;
  /** Отказ сервера приходит отклонённым промисом. */
  saveRegistration: (patch: UpdateAdminRegistrationRequest) => Promise<unknown>;
  saveAuth: (passwordEnabled: boolean) => Promise<unknown>;
  saveSmtp: (patch: UpdateAdminSmtpRequest) => Promise<unknown>;
  test: SmtpTest;
  onSaved?: () => void;
};

/**
 * Регистрация, способы входа и почта: правки всех разделов сохраняет одна
 * панель внизу страницы. Значения, заданные окружением, только читаются.
 */
export const AuthSettingsForm = ({
  registration,
  auth,
  smtp,
  oidc,
  saveRegistration,
  saveAuth,
  saveSmtp,
  test,
  onSaved,
}: AuthSettingsFormProps) => {
  const { t } = useTranslation("adminSettings");
  const reg = useDraft<RegistrationDraft>(
    registrationDraftOf(registration),
    (key) => !isLocked(registration.fields, REGISTRATION_FIELD[key]),
  );
  const sign = useDraft<SignInDraft>(
    { password: auth.password_enabled },
    () => !isLocked(auth.fields, "auth.password_enabled"),
  );
  const mail = useDraft<SmtpDraft>(
    smtpDraftOf(smtp),
    (key) => !isLocked(smtp.fields, `smtp.${key}`),
  );
  const [touched, setTouched] = useState(false);
  const [busy, setBusy] = useState(false);
  const [failure, setFailure] = useState<string | null>(null);

  // Домены сравниваются по смыслу: «hse.ru,edu.hse.ru» и «hse.ru, edu.hse.ru» одно и то же.
  const domains = parseDomains(reg.value.domains);
  const domainsChanged =
    reg.isChanged("domains") &&
    domains.join(",") !== registration.registration_domains.join(",");
  const regChanged = [
    reg.isChanged("mode"),
    domainsChanged,
    reg.isChanged("approval"),
  ].filter(Boolean).length;

  const domainsEditable = !isLocked(
    registration.fields,
    REGISTRATION_FIELD.domains,
  );
  const badDomains = invalidDomains(domains);
  const domainsError =
    reg.value.mode === "domains" &&
    domainsEditable &&
    (regChanged > 0 || touched)
      ? domains.length === 0
        ? t("registration.domainsRequired")
        : badDomains.length > 0
          ? t("registration.domainsInvalid", { list: badDomains.join(", ") })
          : undefined
      : undefined;

  const smtpIssues = validateSmtp(mail.value);
  const shownSmtp: SmtpIssues = Object.fromEntries(
    Object.entries(smtpIssues).filter(
      ([key]) =>
        !isLocked(smtp.fields, `smtp.${key}`) &&
        (touched || mail.isChanged(key as keyof SmtpDraft)),
    ),
  );
  const smtpBlocked = mail.changed.some(
    (key) => smtpIssues[key as keyof SmtpIssues] !== undefined,
  );
  const invalid = (regChanged > 0 && domainsError !== undefined) || smtpBlocked;
  const dirtyCount = regChanged + sign.changed.length + mail.changed.length;

  const discard = () => {
    reg.reset();
    sign.reset();
    mail.reset();
    setTouched(false);
    setFailure(null);
  };

  const save = async () => {
    setTouched(true);
    if (dirtyCount === 0 || invalid || busy) return;
    setBusy(true);
    setFailure(null);
    const text = (key: keyof SmtpDraft): string | null =>
      mail.isChanged(key) ? mail.value[key].trim() : null;
    const result = await settleSaves([
      regChanged > 0 && {
        run: () =>
          saveRegistration({
            registration_mode: reg.isChanged("mode") ? reg.value.mode : null,
            registration_domains: domainsChanged ? domains : null,
            require_approval: reg.isChanged("approval")
              ? reg.value.approval
              : null,
          }),
        done: reg.reset,
      },
      sign.changed.length > 0 && {
        run: () => saveAuth(sign.value.password),
        done: sign.reset,
      },
      mail.changed.length > 0 && {
        run: () =>
          saveSmtp({
            host: text("host"),
            port: mail.isChanged("port") ? Number(mail.value.port) : null,
            security: mail.isChanged("security") ? mail.value.security : null,
            username: text("username"),
            password: mail.isChanged("password") ? mail.value.password : null,
            from_address: text("from_address"),
            from_name: text("from_name"),
          }),
        done: mail.reset,
      },
    ]);
    setBusy(false);
    if (result === null) {
      setTouched(false);
      onSaved?.();
    } else {
      setFailure(t(failureKey(result)));
    }
  };

  return (
    <div className="flex flex-col" style={{ gap: 16, flex: 1 }}>
      <RegistrationSection
        settings={registration}
        draft={reg}
        domainsError={domainsError}
        smtpEnabled={smtp.enabled}
      />
      <SignInSection settings={auth} draft={sign} />
      {oidc}
      <SmtpSection
        settings={smtp}
        draft={mail}
        issues={shownSmtp}
        test={test}
      />
      <StickySaveBar
        dirtyCount={dirtyCount}
        busy={busy}
        saveDisabled={invalid}
        error={failure ?? (invalid ? t("fixFields") : null)}
        onSave={() => {
          void save();
        }}
        onDiscard={discard}
      />
    </div>
  );
};
