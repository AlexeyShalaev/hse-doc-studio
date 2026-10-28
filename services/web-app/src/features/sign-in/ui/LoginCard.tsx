import { useId, useState, type FormEvent } from "react";
import { Link } from "react-router";
import { KeyRound, LogIn } from "lucide-react";
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
}: LoginCardProps) => {
  const { t } = useTranslation("auth");
  const uid = useId();
  const [email, setEmail] = useState(initialEmail);
  const [password, setPassword] = useState("");
  const left = useCountdown(failure?.retryAfter ?? 0, failure);
  const waiting = failure?.code === "rate_limited" && left > 0;
  const showFailure =
    failure !== null && !(failure.code === "rate_limited" && left <= 0);
  const hasSso = auth.oidc_providers.length > 0;
  const canRegister = auth.registration_mode !== "closed";
  const errorId = `${uid}-error`;

  const submit = (event: FormEvent) => {
    event.preventDefault();
    if (pending || waiting) return;
    onSubmit(email.trim(), password);
  };

  return (
    <section data-testid="auth-screen-login" aria-labelledby={`${uid}-title`}>
      <h1
        id={`${uid}-title`}
        style={{ fontSize: 20, fontWeight: 600, margin: "0 0 6px" }}
      >
        {t("pages.login.title")}
      </h1>
      <p style={{ margin: "0 0 18px", color: "var(--fg-2)", fontSize: 13.5 }}>
        {auth.password_enabled ? t("pages.login.body") : t("login.ssoOnlyBody")}
      </p>

      {sessionEnded && !showFailure && (
        <div style={{ marginBottom: 16 }}>
          <ResultFrame
            tone="info"
            role="status"
            testId="login-session-ended"
            title={t("login.sessionEnded")}
          >
            <p style={{ margin: 0, fontSize: 12.5, color: "var(--fg-2)" }}>
              {t("login.sessionEndedHint")}
            </p>
          </ResultFrame>
        </div>
      )}

      {showFailure && (
        <div id={errorId} style={{ marginBottom: 16 }}>
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
                  style={{ margin: 0, fontSize: 12.5, color: "var(--fg-2)" }}
                >
                  {t("login.retryIn", { count: left })}
                </p>
              </>
            )}
            {failure.code !== "rate_limited" && (
              <p style={{ margin: 0, fontSize: 12.5, color: "var(--fg-2)" }}>
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
          style={{ gap: 14 }}
          aria-describedby={showFailure ? errorId : undefined}
          data-testid="login-form"
        >
          <Input
            id={`${uid}-email`}
            label={t("login.email")}
            type="email"
            name="email"
            autoComplete="username"
            autoFocus
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
          <div className="flex justify-end" style={{ marginTop: -6 }}>
            <Link
              to="/forgot"
              style={{ color: "var(--accent)", fontSize: 12.5 }}
            >
              {t("links.forgot")}
            </Link>
          </div>
          <Button
            type="submit"
            disabled={waiting || email === "" || password === ""}
            aria-disabled={pending}
            style={{ justifyContent: "center", gap: 8 }}
          >
            {pending ? (
              <Spinner size="sm" />
            ) : (
              <LogIn size={15} aria-hidden="true" />
            )}
            {pending ? t("login.submitting") : t("login.submit")}
          </Button>
        </form>
      )}

      {hasSso && (
        <div data-testid="login-sso">
          {auth.password_enabled && (
            <div
              className="flex items-center"
              style={{
                gap: 10,
                margin: "18px 0",
                color: "var(--fg-3)",
                fontSize: 12,
              }}
              role="separator"
              aria-label={t("login.or")}
            >
              <span style={{ flex: 1, height: 1, background: "var(--line)" }} />
              {t("login.or")}
              <span style={{ flex: 1, height: 1, background: "var(--line)" }} />
            </div>
          )}
          <div className="flex flex-col" style={{ gap: 8 }}>
            {auth.oidc_providers.map((provider) => (
              <Button key={provider.id} variant="secondary" asChild>
                <a
                  href={ssoHref(provider.id)}
                  style={{ justifyContent: "center", gap: 8 }}
                >
                  <KeyRound size={15} aria-hidden="true" />
                  {t("login.sso", { name: provider.label })}
                </a>
              </Button>
            ))}
          </div>
        </div>
      )}

      {!auth.password_enabled && !hasSso && (
        <p
          data-testid="login-no-methods"
          style={{ color: "var(--fg-2)", fontSize: 13 }}
        >
          {t("login.noMethods")}
        </p>
      )}

      {canRegister && (
        <p style={{ margin: "20px 0 0", fontSize: 13, color: "var(--fg-2)" }}>
          {t("login.noAccount")}{" "}
          <Link to="/register" style={{ color: "var(--accent)" }}>
            {t("links.register")}
          </Link>
        </p>
      )}
    </section>
  );
};
