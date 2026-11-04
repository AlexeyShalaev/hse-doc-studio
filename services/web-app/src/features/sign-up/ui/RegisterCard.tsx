import { useId, useState, type FormEvent } from "react";
import { Link } from "react-router";
import { FingerprintPattern, UserPlus } from "lucide-react";
import { useTranslation } from "react-i18next";
import { Button, Input, Spinner } from "@shared/ui";
import { ResultFrame } from "@shared/ui/ResultFrame";
import type { AuthOptions, InvitationInfo } from "@entities/session";
import { fieldOfFailure, registerErrorKey } from "../lib/registerErrors";

// exactOptionalPropertyTypes: пустое значение не передаётся вовсе.
const errorProp = (error: string | undefined) => (error ? { error } : {});
const hintProp = (hint: string | undefined) => (hint ? { hint } : {});

export type RegisterCardProps = {
  auth: AuthOptions;
  /** Приглашение: почта подставлена и заблокирована. */
  invitation?: InvitationInfo | null;
  pending?: boolean;
  failure?: { code: string } | null;
  onSubmit: (input: { name: string; email: string; password: string }) => void;
  /** Регистрация по приглашению сразу с passkey: кнопка над полями пароля, имя берётся из формы. */
  passkey?: {
    available: boolean;
    pending: boolean;
    onStart: (name: string) => void;
  };
  initialName?: string;
  initialEmail?: string;
};

/**
 * Форма регистрации для режимов open, domains и по приглашению. Подсказка над
 * формой зависит от режима. Отказы по полям (домен, пароль) стоят у поля,
 * остальные над формой.
 */
export const RegisterCard = ({
  auth,
  invitation = null,
  pending = false,
  failure = null,
  onSubmit,
  passkey,
  initialName = "",
  initialEmail = "",
}: RegisterCardProps) => {
  const { t } = useTranslation("auth");
  const uid = useId();
  const [name, setName] = useState(initialName);
  const [email, setEmail] = useState(invitation?.email ?? initialEmail);
  const [password, setPassword] = useState("");
  const [confirm, setConfirm] = useState("");
  const [touched, setTouched] = useState(false);

  const min = auth.password_min_length;
  const tooShort = password.length > 0 && password.length < min;
  const mismatch = confirm.length > 0 && confirm !== password;
  const valid =
    name.trim() !== "" &&
    email.trim() !== "" &&
    password.length >= min &&
    confirm === password;

  const hasPasskey = passkey?.available === true;
  // Без входа по паролю (только SSO) аккаунт по приглашению создаётся только с passkey.
  const withPassword = auth.password_enabled;
  const busy = pending || (passkey?.pending ?? false);

  const field = failure ? fieldOfFailure(failure.code) : null;
  const showFrame = failure !== null && field === null;
  const errorId = `${uid}-error`;

  const hint = invitation
    ? hasPasskey && !withPassword
      ? t("register.hint.invitedPasskey", { who: invitation.invited_by })
      : invitation.org_name
        ? t("register.hint.invitedOrg", {
            who: invitation.invited_by,
            org: invitation.org_name,
          })
        : t("register.hint.invited", { who: invitation.invited_by })
    : auth.registration_mode === "domains"
      ? t("register.hint.domains")
      : t("pages.register.body");

  const submit = (event: FormEvent) => {
    event.preventDefault();
    setTouched(true);
    if (busy || !valid) return;
    onSubmit({ name: name.trim(), email: email.trim(), password });
  };

  return (
    <section
      data-testid="auth-screen-register"
      data-mode={invitation ? "invitation" : auth.registration_mode}
      aria-labelledby={`${uid}-title`}
    >
      <h1
        id={`${uid}-title`}
        style={{ fontSize: "1.25rem", fontWeight: 600, margin: "0 0 0.375rem" }}
      >
        {invitation ? t("pages.invite.title") : t("pages.register.title")}
      </h1>
      <p
        data-testid="register-hint"
        style={{
          margin: "0 0 1.125rem",
          color: "var(--fg-2)",
          fontSize: "0.84375rem",
        }}
      >
        {hint}
      </p>

      {showFrame && (
        <div id={errorId} style={{ marginBottom: "1rem" }}>
          <ResultFrame
            tone={failure.code === "rate_limited" ? "warn" : "err"}
            role="alert"
            testId="register-error"
            title={t(registerErrorKey(failure.code))}
          >
            <p
              style={{
                margin: 0,
                fontSize: "0.78125rem",
                color: "var(--fg-2)",
              }}
            >
              {t(`${registerErrorKey(failure.code)}Hint`, {
                defaultValue: "",
              })}
            </p>
          </ResultFrame>
        </div>
      )}

      <form
        onSubmit={submit}
        className="flex flex-col"
        style={{ gap: "0.875rem" }}
        aria-describedby={showFrame ? errorId : undefined}
        data-testid="register-form"
      >
        <Input
          id={`${uid}-name`}
          label={t("register.name")}
          name="name"
          autoComplete="name"
          autoFocus={!invitation}
          required
          value={name}
          onChange={(e) => {
            setName(e.target.value);
          }}
          readOnly={pending}
        />
        <Input
          id={`${uid}-email`}
          label={t("register.email")}
          type="email"
          name="email"
          autoComplete="username"
          required
          value={email}
          readOnly={invitation !== null || pending}
          onChange={(e) => {
            setEmail(e.target.value);
          }}
          {...hintProp(invitation ? t("register.emailLocked") : undefined)}
          {...errorProp(
            field === "email"
              ? t(registerErrorKey(failure?.code ?? ""))
              : undefined,
          )}
        />
        {hasPasskey && (
          <div data-testid="register-passkey-block">
            <Button
              type="button"
              variant={withPassword ? "secondary" : "primary"}
              data-testid="register-passkey"
              disabled={name.trim() === "" || email.trim() === ""}
              aria-disabled={busy}
              onClick={() => {
                if (!busy) passkey.onStart(name.trim());
              }}
              style={{ justifyContent: "center", gap: "0.5rem", width: "100%" }}
            >
              {passkey.pending ? (
                <Spinner size="sm" />
              ) : (
                <FingerprintPattern size="0.9375rem" aria-hidden="true" />
              )}
              {passkey.pending
                ? t("register.passkeyPending")
                : t("register.passkey")}
            </Button>
            <p
              style={{
                margin: "0.375rem 0 0",
                fontSize: "0.75rem",
                color: "var(--fg-3)",
              }}
            >
              {t("register.passkeyHint")}
            </p>
            {withPassword && (
              <div
                className="flex items-center"
                style={{
                  gap: "0.625rem",
                  margin: "0.875rem 0 0",
                  color: "var(--fg-3)",
                  fontSize: "0.75rem",
                }}
                role="separator"
                aria-label={t("register.orPassword")}
              >
                <span
                  style={{ flex: 1, height: 1, background: "var(--line)" }}
                />
                {t("register.orPassword")}
                <span
                  style={{ flex: 1, height: 1, background: "var(--line)" }}
                />
              </div>
            )}
          </div>
        )}
        {withPassword && (
          <>
            <Input
              id={`${uid}-password`}
              label={t("register.password")}
              type="password"
              name="password"
              autoComplete="new-password"
              required
              value={password}
              onChange={(e) => {
                setPassword(e.target.value);
              }}
              readOnly={pending}
              hint={t("register.passwordHint", { count: min })}
              {...errorProp(
                field === "password"
                  ? t(registerErrorKey(failure?.code ?? ""))
                  : touched && tooShort
                    ? t("register.passwordShort", { count: min })
                    : undefined,
              )}
            />
            <Input
              id={`${uid}-confirm`}
              label={t("register.confirm")}
              type="password"
              name="confirm"
              autoComplete="new-password"
              required
              value={confirm}
              onChange={(e) => {
                setConfirm(e.target.value);
              }}
              readOnly={pending}
              {...errorProp(mismatch ? t("register.mismatch") : undefined)}
            />
            <Button
              type="submit"
              aria-disabled={pending}
              style={{ justifyContent: "center", gap: "0.5rem" }}
            >
              {pending ? (
                <Spinner size="sm" />
              ) : (
                <UserPlus size="0.9375rem" aria-hidden="true" />
              )}
              {pending ? t("register.submitting") : t("register.submit")}
            </Button>
          </>
        )}
      </form>

      <p
        style={{
          margin: "1.25rem 0 0",
          fontSize: "0.8125rem",
          color: "var(--fg-2)",
        }}
      >
        {t("register.haveAccount")}{" "}
        <Link to="/login" style={{ color: "var(--accent)" }}>
          {t("register.toLogin")}
        </Link>
      </p>
    </section>
  );
};
