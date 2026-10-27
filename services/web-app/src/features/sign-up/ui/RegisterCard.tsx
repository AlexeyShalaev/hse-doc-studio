import { useId, useState, type FormEvent } from "react";
import { Link } from "react-router";
import { UserPlus } from "lucide-react";
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

  const field = failure ? fieldOfFailure(failure.code) : null;
  const showFrame = failure !== null && field === null;
  const errorId = `${uid}-error`;

  const hint = invitation
    ? invitation.org_name
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
    if (pending || !valid) return;
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
        style={{ fontSize: 20, fontWeight: 600, margin: "0 0 6px" }}
      >
        {invitation ? t("pages.invite.title") : t("pages.register.title")}
      </h1>
      <p
        data-testid="register-hint"
        style={{ margin: "0 0 18px", color: "var(--fg-2)", fontSize: 13.5 }}
      >
        {hint}
      </p>

      {showFrame && (
        <div id={errorId} style={{ marginBottom: 16 }}>
          <ResultFrame
            tone={failure.code === "rate_limited" ? "warn" : "err"}
            role="alert"
            testId="register-error"
            title={t(registerErrorKey(failure.code))}
          >
            <p style={{ margin: 0, fontSize: 12.5, color: "var(--fg-2)" }}>
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
        style={{ gap: 14 }}
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
          disabled={pending}
        />
        <Input
          id={`${uid}-email`}
          label={t("register.email")}
          type="email"
          name="email"
          autoComplete="username"
          required
          value={email}
          readOnly={invitation !== null}
          onChange={(e) => {
            setEmail(e.target.value);
          }}
          disabled={pending}
          {...hintProp(invitation ? t("register.emailLocked") : undefined)}
          {...errorProp(
            field === "email"
              ? t(registerErrorKey(failure?.code ?? ""))
              : undefined,
          )}
        />
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
          disabled={pending}
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
          disabled={pending}
          {...errorProp(mismatch ? t("register.mismatch") : undefined)}
        />
        <Button
          type="submit"
          disabled={pending}
          style={{ justifyContent: "center", gap: 8 }}
        >
          {pending ? (
            <Spinner size="sm" />
          ) : (
            <UserPlus size={15} aria-hidden="true" />
          )}
          {pending ? t("register.submitting") : t("register.submit")}
        </Button>
      </form>

      <p style={{ margin: "20px 0 0", fontSize: 13, color: "var(--fg-2)" }}>
        {t("register.haveAccount")}{" "}
        <Link to="/login" style={{ color: "var(--accent)" }}>
          {t("register.toLogin")}
        </Link>
      </p>
    </section>
  );
};
