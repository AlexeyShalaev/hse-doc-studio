import { useId, useState, type FormEvent } from "react";
import { Link } from "react-router";
import { FingerprintPattern, KeyRound, LogIn } from "lucide-react";
import { useTranslation } from "react-i18next";
import { Button, Input, Spinner } from "@shared/ui";
import { ResultFrame } from "@shared/ui/ResultFrame";
import type { AuthOptions } from "@entities/session";
import {
  loginErrorKey,
  loginErrorTone,
  type LoginFailure,
} from "../lib/loginErrors";
import { useCountdown } from "../lib/useCountdown";

export type LoginCardProps = {
  auth: AuthOptions;
  pending?: boolean;
  failure?: LoginFailure | null;
  /** Сессия закончилась сама: показываем пояснение, откуда экран входа. */
  sessionEnded?: boolean;
  /** Куда ведёт кнопка внешнего входа. */
  ssoHref: (providerId: string) => string;
  onSubmit: (email: string, password: string) => void;
  initialEmail?: string;
  /** Вход по passkey: кнопка и подсказки автозаполнения в поле почты. */
  passkey?: { available: boolean; pending: boolean; onStart: () => void };
  /**
   * Заголовок карточки. На лендинге страница уже имеет свой h1, поэтому там h2,
   * а в диалоге заголовок даёт сам диалог (false).
   */
  heading?: "h1" | "h2" | false;
  /** Фокус в поле почты при показе: на лендинге выключен, чтобы страница не прыгала. */
  autoFocus?: boolean;
};

/**
 * Экран входа: форма пароля, кнопки внешних провайдеров и отказ по коду.
 * Без пароля (SSO-only) формы нет вовсе, остаются только кнопки.
 */
export const LoginCard = ({
  auth,
  pending = false,
  failure = null,
  sessionEnded = false,
  ssoHref,
  onSubmit,
  initialEmail = "",
  passkey,
  heading = "h1",
  autoFocus = true,
}: LoginCardProps) => {
  const Heading = heading === false ? null : heading;
  const { t } = useTranslation("auth");
  const uid = useId();
  const [email, setEmail] = useState(initialEmail);
  const [password, setPassword] = useState("");
  const left = useCountdown(failure?.retryAfter ?? 0, failure);
  const waiting = failure?.code === "rate_limited" && left > 0;
  const showFailure =
    failure !== null && !(failure.code === "rate_limited" && left <= 0);
  const hasSso = auth.oidc_providers.length > 0;
  const hasPasskey = passkey?.available === true;
  // Ссылка только там, где форма регистрации откроется: при «по приглашению»
  // и без пароля она вела бы на экран-тупик.
  const canRegister =
    auth.password_enabled &&
    (auth.registration_mode === "open" || auth.registration_mode === "domains");
  const errorId = `${uid}-error`;

  const submit = (event: FormEvent) => {
    event.preventDefault();
    if (pending || waiting) return;
    onSubmit(email.trim(), password);
  };

  return (
    <section
      data-testid="auth-screen-login"
      aria-labelledby={Heading ? `${uid}-title` : undefined}
      aria-label={Heading ? undefined : t("pages.login.title")}
    >
      {Heading && (
        <Heading
          id={`${uid}-title`}
          style={{
            fontSize: "1.25rem",
            fontWeight: 600,
            margin: "0 0 0.375rem",
          }}
        >
          {t("pages.login.title")}
        </Heading>
      )}
      <p
        style={{
          margin: "0 0 1.125rem",
          color: "var(--fg-2)",
          fontSize: "0.84375rem",
        }}
      >
        {auth.password_enabled ? t("pages.login.body") : t("login.ssoOnlyBody")}
      </p>

      {sessionEnded && !showFailure && (
        <div style={{ marginBottom: "1rem" }}>
          <ResultFrame
            tone="info"
            role="status"
            testId="login-session-ended"
            title={t("login.sessionEnded")}
          >
            <p
              style={{
                margin: 0,
                fontSize: "0.78125rem",
                color: "var(--fg-2)",
              }}
            >
              {t("login.sessionEndedHint")}
            </p>
          </ResultFrame>
        </div>
      )}

      {showFailure && (
        <div id={errorId} style={{ marginBottom: "1rem" }}>
          <ResultFrame
            tone={loginErrorTone(failure.code)}
            role="alert"
            testId="login-error"
            title={t(loginErrorKey(failure.code))}
          >
            {waiting && (
              <>
                {/* Тикающее число скринридер не читает: иначе role=alert
                    повторял бы его каждую секунду. Время объявляется один раз. */}
                <span className="sr-only" data-testid="login-countdown-static">
                  {t("login.retryIn", { count: failure.retryAfter ?? left })}
                </span>
                <p
                  data-testid="login-countdown"
                  aria-hidden="true"
                  className="mono"
                  style={{
                    margin: 0,
                    fontSize: "0.78125rem",
                    color: "var(--fg-2)",
                  }}
                >
                  {t("login.retryIn", { count: left })}
                </p>
              </>
            )}
            {failure.code !== "rate_limited" && (
              <p
                style={{
                  margin: 0,
                  fontSize: "0.78125rem",
                  color: "var(--fg-2)",
                }}
              >
                {t(`${loginErrorKey(failure.code)}Hint`, { defaultValue: "" })}
              </p>
            )}
          </ResultFrame>
        </div>
      )}

      {auth.password_enabled && (
        <form
          onSubmit={submit}
          noValidate={false}
          className="flex flex-col"
          style={{ gap: "0.875rem" }}
          aria-describedby={showFailure ? errorId : undefined}
          data-testid="login-form"
        >
          <Input
            id={`${uid}-email`}
            label={t("login.email")}
            type="email"
            name="email"
            autoComplete={hasPasskey ? "username webauthn" : "username"}
            autoFocus={autoFocus}
            required
            value={email}
            onChange={(e) => {
              setEmail(e.target.value);
            }}
            readOnly={pending}
          />
          <Input
            id={`${uid}-password`}
            label={t("login.password")}
            type="password"
            name="password"
            autoComplete="current-password"
            required
            value={password}
            onChange={(e) => {
              setPassword(e.target.value);
            }}
            readOnly={pending}
          />
          <div className="flex justify-end" style={{ marginTop: "-0.375rem" }}>
            <Link
              to="/forgot"
              style={{ color: "var(--accent)", fontSize: "0.78125rem" }}
            >
              {t("links.forgot")}
            </Link>
          </div>
          <Button
            type="submit"
            disabled={waiting || email === "" || password === ""}
            aria-disabled={pending}
            style={{ justifyContent: "center", gap: "0.5rem" }}
          >
            {pending ? (
              <Spinner size="sm" />
            ) : (
              <LogIn size="0.9375rem" aria-hidden="true" />
            )}
            {pending ? t("login.submitting") : t("login.submit")}
          </Button>
        </form>
      )}

      {hasPasskey && (
        <div data-testid="login-passkey-block">
          {auth.password_enabled && (
            <div
              className="flex items-center"
              style={{
                gap: "0.625rem",
                margin: "1.125rem 0",
                color: "var(--fg-3)",
                fontSize: "0.75rem",
              }}
              role="separator"
              aria-label={t("login.or")}
            >
              <span style={{ flex: 1, height: 1, background: "var(--line)" }} />
              {t("login.or")}
              <span style={{ flex: 1, height: 1, background: "var(--line)" }} />
            </div>
          )}
          <Button
            type="button"
            variant="secondary"
            data-testid="login-passkey"
            aria-disabled={passkey.pending}
            disabled={waiting}
            onClick={() => {
              if (!passkey.pending) passkey.onStart();
            }}
            style={{ justifyContent: "center", gap: "0.5rem", width: "100%" }}
          >
            {passkey.pending ? (
              <Spinner size="sm" />
            ) : (
              <FingerprintPattern size="0.9375rem" aria-hidden="true" />
            )}
            {passkey.pending ? t("login.passkeyPending") : t("login.passkey")}
          </Button>
        </div>
      )}

      {hasSso && (
        <div data-testid="login-sso">
          {(auth.password_enabled || hasPasskey) && (
            <div
              className="flex items-center"
              style={{
                gap: "0.625rem",
                margin: "1.125rem 0",
                color: "var(--fg-3)",
                fontSize: "0.75rem",
              }}
              role="separator"
              aria-label={t("login.or")}
            >
              <span style={{ flex: 1, height: 1, background: "var(--line)" }} />
              {t("login.or")}
              <span style={{ flex: 1, height: 1, background: "var(--line)" }} />
            </div>
          )}
          <div className="flex flex-col" style={{ gap: "0.5rem" }}>
            {auth.oidc_providers.map((provider) => (
              <Button key={provider.id} variant="secondary" asChild>
                <a
                  href={ssoHref(provider.id)}
                  style={{
                    justifyContent: "center",
                    gap: "0.5rem",
                    textDecoration: "none",
                  }}
                >
                  <KeyRound size="0.9375rem" aria-hidden="true" />
                  {t("login.sso", { name: provider.label })}
                </a>
              </Button>
            ))}
          </div>
        </div>
      )}

      {!auth.password_enabled && !hasSso && !hasPasskey && (
        <p
          data-testid="login-no-methods"
          style={{ color: "var(--fg-2)", fontSize: "0.8125rem" }}
        >
          {t("login.noMethods")}
        </p>
      )}

      {canRegister && (
        <p
          style={{
            margin: "1.25rem 0 0",
            fontSize: "0.8125rem",
            color: "var(--fg-2)",
          }}
        >
          {t("login.noAccount")}{" "}
          <Link to="/register" style={{ color: "var(--accent)" }}>
            {t("links.register")}
          </Link>
        </p>
      )}
    </section>
  );
};
