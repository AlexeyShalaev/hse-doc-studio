import { useId, useState } from "react";
import { Mail, Save, Send } from "lucide-react";
import { useTranslation } from "react-i18next";
import { Badge, Button, Input, ResultFrame, Select, Spinner } from "@shared/ui";
import { Notice } from "@shared/ui/ConflictKit";
import type {
  AdminSmtpSettings,
  AdminSmtpTestResult,
  UpdateAdminSmtpRequest,
} from "@entities/session";
import { failureKey, type Failure } from "../lib/failure";
import { ACTIONS, HINT } from "../lib/styles";
import {
  DEFAULT_PORT,
  isEmail,
  validateSmtp,
  type SmtpDraft,
} from "../lib/validate";
import { isLocked } from "../lib/locked";
import { AllLockedNote, LockedBadge, SettingsCard } from "./parts";

export type SmtpCardProps = {
  settings: AdminSmtpSettings;
  pending?: boolean;
  failure?: Failure | null;
  saved?: boolean;
  onSave: (patch: UpdateAdminSmtpRequest) => void;
  /** Тестовое письмо. */
  test: {
    pending?: boolean;
    result?: AdminSmtpTestResult | null;
    failure?: Failure | null;
    /** Почта администратора: куда уйдёт письмо, если адрес не указан. */
    defaultTo?: string;
    onSend: (to: string | null) => void;
  };
};

const SECURITY = ["starttls", "tls", "none"] as const;

const draftOf = (settings: AdminSmtpSettings): SmtpDraft => ({
  host: settings.host ?? "",
  port: String(settings.port),
  security: settings.security,
  username: settings.username ?? "",
  // Пароль сервер не отдаёт: поле пустое, пока человек не введёт новый.
  password: "",
  from_address: settings.from_address,
  from_name: settings.from_name,
});

/** Почтовый сервер: параметры, пароль только на запись и тестовое письмо. */
export const SmtpCard = ({
  settings,
  pending = false,
  failure = null,
  saved = false,
  onSave,
  test,
}: SmtpCardProps) => {
  const { t } = useTranslation("adminSettings");
  const uid = useId();
  const [draft, setDraft] = useState<SmtpDraft>(draftOf(settings));
  const [touched, setTouched] = useState(false);
  const [to, setTo] = useState("");
  const set = (patch: Partial<SmtpDraft>) => {
    setDraft((d) => ({ ...d, ...patch }));
  };
  const lock = (key: string) => isLocked(settings.fields, `smtp.${key}`);
  const allLocked = (
    [
      "host",
      "port",
      "security",
      "username",
      "password",
      "from_address",
      "from_name",
    ] as const
  ).every(lock);

  const issues = validateSmtp(draft);
  const shown = (key: keyof typeof issues): { error?: string } => {
    const code = touched ? issues[key] : undefined;
    return code ? { error: t(`smtp.issue.${code}`) } : {};
  };

  const base = draftOf(settings);
  const changed = (key: keyof SmtpDraft): boolean =>
    !lock(key) && draft[key] !== base[key];
  const dirty = (Object.keys(base) as (keyof SmtpDraft)[]).some(changed);

  const submit = () => {
    setTouched(true);
    // Замкнутые поля не проверяем: их значение задаёт окружение.
    const relevant = Object.keys(issues).filter(
      (k) => !lock(k as "host" | "port" | "from_address"),
    );
    if (!dirty || relevant.length > 0 || pending) return;
    onSave({
      host: changed("host") ? draft.host.trim() : null,
      port: changed("port") ? Number(draft.port) : null,
      security: changed("security") ? draft.security : null,
      username: changed("username") ? draft.username.trim() : null,
      password: changed("password") ? draft.password : null,
      from_address: changed("from_address") ? draft.from_address.trim() : null,
      from_name: changed("from_name") ? draft.from_name.trim() : null,
    });
  };

  const toValue = to.trim();
  const toInvalid = toValue !== "" && !isEmail(toValue);
  const canTest = settings.enabled && !dirty && !toInvalid && !test.pending;

  const field = (
    key: keyof SmtpDraft,
    label: string,
    extra: Partial<React.ComponentProps<typeof Input>> = {},
  ) => (
    <div className="flex flex-col" style={{ gap: 6, minWidth: 0 }}>
      <Input
        id={`${uid}-${key}`}
        label={label}
        value={draft[key]}
        readOnly={lock(key)}
        onChange={(e) => {
          set({ [key]: e.target.value });
        }}
        {...extra}
      />
      {lock(key) && <LockedBadge testId={`locked-smtp-${key}`} />}
    </div>
  );

  return (
    <SettingsCard
      id="admin-smtp"
      testId="admin-smtp"
      title={t("smtp.title")}
      sub={t("smtp.sub")}
      aside={
        <Badge
          variant={settings.enabled ? "success" : "subtle"}
          data-testid="smtp-status"
        >
          {settings.enabled ? t("smtp.on") : t("smtp.off")}
        </Badge>
      }
    >
      {!settings.enabled && <Notice tone="info" text={t("smtp.offNote")} />}
      <form
        onSubmit={(e) => {
          e.preventDefault();
          submit();
        }}
        className="flex flex-col"
        style={{ gap: 12 }}
        data-testid="smtp-form"
      >
        <div
          style={{
            display: "grid",
            gap: 12,
            gridTemplateColumns: "repeat(auto-fit, minmax(200px, 1fr))",
          }}
        >
          {field("host", t("smtp.host"), {
            isMono: true,
            placeholder: "smtp.example.org",
            ...shown("host"),
          })}
          {field("port", t("smtp.port"), {
            isMono: true,
            inputMode: "numeric",
            ...shown("port"),
          })}
        </div>

        <div className="flex flex-col" style={{ gap: 6 }}>
          <label
            htmlFor={`${uid}-security`}
            style={{ fontSize: 12.5, fontWeight: 600 }}
          >
            {t("smtp.security")}
          </label>
          <Select
            id={`${uid}-security`}
            value={draft.security}
            isDisabled={lock("security")}
            onValueChange={(v) => {
              const security = v as SmtpDraft["security"];
              // Порт по умолчанию следует за защитой, пока человек не ввёл свой.
              const untouchedPort = Object.values<number>(
                DEFAULT_PORT,
              ).includes(Number(draft.port));
              set({
                security,
                ...(untouchedPort && !lock("port")
                  ? { port: String(DEFAULT_PORT[security]) }
                  : {}),
              });
            }}
            options={SECURITY.map((value) => ({
              value,
              label: t(`smtp.securityOption.${value}`),
            }))}
          />
          {lock("security") && <LockedBadge testId="locked-smtp-security" />}
        </div>

        <div
          style={{
            display: "grid",
            gap: 12,
            gridTemplateColumns: "repeat(auto-fit, minmax(200px, 1fr))",
          }}
        >
          {field("username", t("smtp.username"), {
            autoComplete: "off",
            isMono: true,
          })}
          <div className="flex flex-col" style={{ gap: 6, minWidth: 0 }}>
            {field("password", t("smtp.password"), {
              type: "password",
              name: "smtp-password",
              autoComplete: "new-password",
              placeholder: settings.password_set ? t("smtp.passwordKeep") : "",
              hint: t("smtp.passwordHint"),
            })}
            {settings.password_set && (
              <span
                className="chip subtle"
                style={{ alignSelf: "flex-start" }}
                data-testid="smtp-password-set"
              >
                {t("smtp.passwordSet")}
              </span>
            )}
          </div>
        </div>

        <div
          style={{
            display: "grid",
            gap: 12,
            gridTemplateColumns: "repeat(auto-fit, minmax(200px, 1fr))",
          }}
        >
          {field("from_address", t("smtp.fromAddress"), {
            isMono: true,
            inputMode: "email",
            ...shown("from_address"),
          })}
          {field("from_name", t("smtp.fromName"))}
        </div>

        {failure && (
          <Notice tone="err" role="alert" text={t(failureKey(failure.code))} />
        )}
        {saved && !failure && !dirty && (
          <ResultFrame
            tone="ok"
            role="status"
            testId="smtp-saved"
            title={t("saved")}
          />
        )}
        {allLocked ? (
          <AllLockedNote />
        ) : (
          <div style={ACTIONS}>
            <Button
              type="submit"
              aria-disabled={!dirty || pending}
              style={{ gap: 8 }}
              data-testid="smtp-save"
            >
              {pending ? (
                <Spinner size="sm" />
              ) : (
                <Save size={14} aria-hidden="true" />
              )}
              {pending ? t("saving") : t("save")}
            </Button>
          </div>
        )}
      </form>

      <div
        className="flex flex-col"
        style={{
          gap: 10,
          paddingTop: 14,
          borderTop: "1px solid var(--border)",
        }}
        data-testid="smtp-test"
      >
        <div className="flex flex-col" style={{ gap: 2 }}>
          <strong style={{ fontSize: 13 }}>{t("smtp.test.title")}</strong>
          <span style={HINT}>{t("smtp.test.sub")}</span>
        </div>
        <form
          className="flex"
          style={{ gap: 8, alignItems: "flex-start", flexWrap: "wrap" }}
          onSubmit={(e) => {
            e.preventDefault();
            if (canTest) test.onSend(toValue === "" ? null : toValue);
          }}
        >
          <div style={{ flex: "1 1 240px", minWidth: 0 }}>
            <Input
              id={`${uid}-to`}
              label={t("smtp.test.to")}
              type="email"
              inputMode="email"
              value={to}
              placeholder={test.defaultTo ?? ""}
              onChange={(e) => {
                setTo(e.target.value);
              }}
              {...(toInvalid
                ? { error: t("smtp.issue.fromInvalid") }
                : { hint: t("smtp.test.toHint") })}
            />
          </div>
          <Button
            type="submit"
            variant="secondary"
            aria-disabled={!canTest}
            style={{ gap: 8, marginTop: 22 }}
            data-testid="smtp-test-send"
          >
            {test.pending ? (
              <Spinner size="sm" />
            ) : (
              <Send size={14} aria-hidden="true" />
            )}
            {test.pending ? t("smtp.test.sending") : t("smtp.test.send")}
          </Button>
        </form>
        {!settings.enabled && (
          <p style={HINT}>
            <Mail
              size={12}
              aria-hidden="true"
              style={{ verticalAlign: -1, marginRight: 4 }}
            />
            {t("smtp.test.needSmtp")}
          </p>
        )}
        {dirty && settings.enabled && (
          <p style={HINT}>{t("smtp.test.saveFirst")}</p>
        )}
        {test.failure && (
          <Notice
            tone="err"
            role="alert"
            text={t(failureKey(test.failure.code))}
          />
        )}
        {test.result?.ok === true && (
          <ResultFrame
            tone="ok"
            role="status"
            testId="smtp-test-ok"
            title={t("smtp.test.ok")}
          />
        )}
        {test.result?.ok === false && (
          <ResultFrame
            tone="err"
            role="alert"
            testId="smtp-test-failed"
            title={t("smtp.test.failed")}
          >
            {test.result.error && (
              <code
                className="mono"
                style={{ fontSize: 11.5, overflowWrap: "anywhere" }}
              >
                {test.result.error}
              </code>
            )}
          </ResultFrame>
        )}
      </div>
    </SettingsCard>
  );
};
