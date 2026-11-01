import { useId, useState, type ReactNode } from "react";
import { Send } from "lucide-react";
import { useTranslation } from "react-i18next";
import type { Draft } from "@shared/lib/useDraft";
import {
  Button,
  Input,
  Section,
  Select,
  SettingRow,
  Spinner,
  StatusDot,
  type InputProps,
} from "@shared/ui";
import { Notice } from "@shared/ui/ConflictKit";
import type { AdminSmtpSettings, AdminSmtpTestResult } from "@entities/session";
import { failureKey, type Failure } from "../lib/failure";
import { isLocked } from "../lib/locked";
import {
  DEFAULT_PORT,
  isEmail,
  type SmtpDraft,
  type SmtpIssues,
} from "../lib/validate";
import { SMTP_KEYS } from "../lib/drafts";
import { AllLockedNote } from "./parts";

export type SmtpTest = {
  pending?: boolean;
  result?: AdminSmtpTestResult | null;
  failure?: Failure | null;
  /** Почта администратора: куда уйдёт письмо, если адрес не указан. */
  defaultTo?: string;
  onSend: (to: string | null) => void;
};

export type SmtpSectionProps = {
  settings: AdminSmtpSettings;
  draft: Draft<SmtpDraft>;
  /** Ошибки полей, которые уже пора показать. */
  issues: SmtpIssues;
  test: SmtpTest;
};

const SECURITY = ["starttls", "tls", "none"] as const;

/** Почтовый сервер: параметры, пароль только на запись и тестовое письмо. */
export const SmtpSection = ({
  settings,
  draft,
  issues,
  test,
}: SmtpSectionProps) => {
  const { t } = useTranslation("adminSettings");
  const uid = useId();
  const [to, setTo] = useState("");
  const [sentTo, setSentTo] = useState<string | null>(null);
  const lock = (key: keyof SmtpDraft) =>
    isLocked(settings.fields, `smtp.${key}`);
  const allLocked = SMTP_KEYS.every(lock);
  const value = draft.value;
  const issue = (key: keyof SmtpIssues): { error?: string } => {
    const code = issues[key];
    return code ? { error: t(`smtp.issue.${code}`) } : {};
  };

  const input = (key: keyof SmtpDraft, extra: Partial<InputProps> = {}) => (
    <Input
      id={`${uid}-${key}`}
      value={value[key]}
      locked={lock(key)}
      autoComplete="off"
      spellCheck={false}
      onChange={(e) => {
        draft.set({ [key]: e.target.value });
      }}
      {...extra}
    />
  );

  const row = (
    key: keyof SmtpDraft,
    label: string,
    hint: ReactNode,
    control: ReactNode,
  ) => (
    <SettingRow
      label={label}
      hint={hint}
      htmlFor={`${uid}-${key}`}
      locked={lock(key)}
      lockStyle={allLocked ? "icon" : "chip"}
      align="stretch"
      testId={`smtp-${key}`}
    >
      {control}
    </SettingRow>
  );

  const toValue = to.trim();
  const toInvalid = toValue !== "" && !isEmail(toValue);
  const dirty = draft.changed.length > 0;
  const canTest = settings.enabled && !dirty && !toInvalid && !test.pending;
  const testBlocker = !settings.enabled
    ? t("smtp.test.needSmtp")
    : dirty
      ? t("smtp.test.saveFirst")
      : null;

  return (
    <Section
      id="admin-smtp"
      testId="admin-smtp"
      title={t("smtp.title")}
      description={t("smtp.sub")}
      actions={
        <span data-testid="smtp-status">
          <StatusDot
            status={settings.enabled ? "success" : "neutral"}
            label={settings.enabled ? t("smtp.on") : t("smtp.off")}
          />
        </span>
      }
      footer={allLocked ? <AllLockedNote /> : null}
    >
      {!settings.enabled && (
        <div className="adm-setting-extra">
          <Notice tone="info" text={t("smtp.offNote")} />
        </div>
      )}
      {row(
        "host",
        t("smtp.host"),
        t("smtp.hostHint"),
        <div className="adm-fields">
          <div className="adm-fields-row">
            {input("host", {
              placeholder: "smtp.example.org",
              ...issue("host"),
            })}
            <div style={{ width: 92, flexShrink: 0 }}>
              {input("port", {
                id: `${uid}-port`,
                "aria-label": t("smtp.port"),
                inputMode: "numeric",
                // Число по правому краю, как в остальных числовых полях.
                style: {
                  textAlign: "right",
                  fontVariantNumeric: "tabular-nums",
                },
                ...issue("port"),
              })}
            </div>
          </div>
        </div>,
      )}
      {row(
        "security",
        t("smtp.security"),
        t("smtp.securityHint"),
        <Select
          id={`${uid}-security`}
          value={value.security}
          isDisabled={lock("security")}
          onValueChange={(v) => {
            const security = v as SmtpDraft["security"];
            // Порт по умолчанию следует за защитой, пока человек не ввёл свой.
            const untouchedPort = Object.values<number>(DEFAULT_PORT).includes(
              Number(value.port),
            );
            draft.set({
              security,
              ...(untouchedPort && !lock("port")
                ? { port: String(DEFAULT_PORT[security]) }
                : {}),
            });
          }}
          options={SECURITY.map((option) => ({
            value: option,
            label: t(`smtp.securityOption.${option}`),
          }))}
        />,
      )}
      {row(
        "username",
        t("smtp.username"),
        t("smtp.usernameHint"),
        input("username"),
      )}
      {row(
        "password",
        t("smtp.password"),
        t("smtp.passwordHint"),
        <div className="adm-fields">
          {input("password", {
            type: "password",
            name: "smtp-password",
            autoComplete: "new-password",
            placeholder: settings.password_set ? t("smtp.passwordKeep") : "",
          })}
          {settings.password_set && (
            <span className="adm-field-note" data-testid="smtp-password-set">
              <StatusDot status="success" label={t("smtp.passwordSet")} />
            </span>
          )}
        </div>,
      )}
      {row(
        "from_address",
        t("smtp.fromAddress"),
        t("smtp.fromAddressHint"),
        input("from_address", {
          inputMode: "email",
          ...issue("from_address"),
        }),
      )}
      {row(
        "from_name",
        t("smtp.fromName"),
        t("smtp.fromNameHint"),
        input("from_name"),
      )}

      <SettingRow
        label={t("smtp.test.title")}
        hint={t("smtp.test.sub")}
        htmlFor={`${uid}-to`}
        align="stretch"
        testId="smtp-test"
      >
        <div className="adm-fields">
          <form
            className="adm-fields-row"
            onSubmit={(e) => {
              e.preventDefault();
              if (!canTest) return;
              setSentTo(toValue === "" ? (test.defaultTo ?? null) : toValue);
              test.onSend(toValue === "" ? null : toValue);
            }}
          >
            <Input
              id={`${uid}-to`}
              aria-label={t("smtp.test.to")}
              type="email"
              inputMode="email"
              value={to}
              placeholder={test.defaultTo ?? t("smtp.test.to")}
              onChange={(e) => {
                setTo(e.target.value);
              }}
              {...(toInvalid ? { error: t("smtp.issue.fromInvalid") } : {})}
            />
            <Button
              type="submit"
              variant="secondary"
              aria-disabled={!canTest}
              style={{ gap: 6, flexShrink: 0 }}
              data-testid="smtp-test-send"
            >
              {test.pending ? (
                <Spinner size="sm" />
              ) : (
                <Send size={13} aria-hidden="true" />
              )}
              {test.pending ? t("smtp.test.sending") : t("smtp.test.send")}
            </Button>
          </form>
          {testBlocker && <p className="adm-field-note">{testBlocker}</p>}
          {test.failure && (
            <Notice
              tone="err"
              role="alert"
              text={t(failureKey(test.failure.code))}
            />
          )}
          {test.result?.ok === true && (
            <span
              className="adm-field-note"
              role="status"
              data-testid="smtp-test-ok"
            >
              <StatusDot
                status="success"
                label={
                  sentTo
                    ? t("smtp.test.okTo", { to: sentTo })
                    : t("smtp.test.ok")
                }
              />
            </span>
          )}
          {test.result?.ok === false && (
            <span
              className="adm-field-note"
              role="alert"
              style={{ flexWrap: "wrap" }}
              data-testid="smtp-test-failed"
            >
              <StatusDot status="danger" label={t("smtp.test.failed")} />
              {test.result.error && (
                <code
                  className="mono"
                  style={{ fontSize: 11, overflowWrap: "anywhere" }}
                >
                  {test.result.error}
                </code>
              )}
            </span>
          )}
        </div>
      </SettingRow>
    </Section>
  );
};
