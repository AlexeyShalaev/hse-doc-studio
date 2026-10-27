import { useId, useState, type FormEvent } from "react";
import { Link } from "react-router";
import { Send } from "lucide-react";
import { useTranslation } from "react-i18next";
import { Button, Input, LinkDelivery, Spinner } from "@shared/ui";
import { ResultFrame } from "@shared/ui/ResultFrame";
import type { RecoveryFailure } from "../lib/recoveryErrors";
import { BackToLogin, FailureFrame, Heading, Note } from "./parts";

export type VerifyState = "checking" | "done" | "invalid" | "unreachable";

export type ResendProps = {
  pending?: boolean;
  failure?: RecoveryFailure | null;
  /** Заполнено после отправки: ответ нейтральный, ссылка только без SMTP. */
  sent?: { email: string; link: string | null } | null;
  smtp: boolean;
  onSubmit: (email: string) => void;
};

export type VerifyCardProps = {
  state: VerifyState;
  resend: ResendProps;
  onRetry?: () => void;
};

const ResendForm = ({
  pending = false,
  failure = null,
  sent = null,
  smtp,
  onSubmit,
}: ResendProps) => {
  const { t } = useTranslation("auth");
  const uid = useId();
  const [email, setEmail] = useState("");
  const submit = (event: FormEvent) => {
    event.preventDefault();
    if (pending || email.trim() === "") return;
    onSubmit(email.trim());
  };
  if (sent) {
    return (
      <div data-testid="verify-resent" style={{ marginTop: 18 }}>
        <ResultFrame
          tone="ok"
          role="status"
          testId="verify-resent-frame"
          title={t("verify.resent.title")}
        >
          <Note>
            {smtp
              ? t("verify.resent.body", { email: sent.email })
              : t("verify.resent.noSmtp")}
          </Note>
        </ResultFrame>
        {sent.link && (
          <div style={{ marginTop: 14 }}>
            <LinkDelivery kind="verify" link={sent.link} once />
          </div>
        )}
      </div>
    );
  }
  return (
    <form
      onSubmit={submit}
      className="flex flex-col"
      style={{ gap: 12, marginTop: 18 }}
      data-testid="verify-resend-form"
    >
      <p style={{ margin: 0, fontSize: 13, color: "var(--fg-2)" }}>
        {t("verify.resend.lead")}
      </p>
      {failure && <FailureFrame failure={failure} testId="verify-error" />}
      <Input
        id={`${uid}-email`}
        label={t("login.email")}
        type="email"
        name="email"
        autoComplete="username"
        required
        value={email}
        onChange={(e) => {
          setEmail(e.target.value);
        }}
        disabled={pending}
      />
      <Button
        type="submit"
        disabled={pending || email.trim() === ""}
        style={{ justifyContent: "center", gap: 8 }}
      >
        {pending ? (
          <Spinner size="sm" />
        ) : (
          <Send size={15} aria-hidden="true" />
        )}
        {pending ? t("verify.resend.submitting") : t("verify.resend.submit")}
      </Button>
    </form>
  );
};

/** Подтверждение почты по ссылке: проверка, успех, просроченная ссылка. */
export const VerifyCard = ({ state, resend, onRetry }: VerifyCardProps) => {
  const { t } = useTranslation("auth");
  return (
    <section data-testid="auth-screen-verify" data-state={state}>
      <Heading>{t("pages.verify.title")}</Heading>
      <div style={{ height: 12 }} />
      {state === "checking" && (
        <div
          className="flex items-center"
          style={{ gap: 10, color: "var(--fg-2)", fontSize: 13.5 }}
          data-testid="verify-checking"
        >
          <Spinner />
          {t("pages.verify.body")}
        </div>
      )}
      {state === "done" && (
        <>
          <ResultFrame
            tone="ok"
            role="status"
            testId="verify-done"
            title={t("verify.done.title")}
          >
            <Note>{t("verify.done.body")}</Note>
          </ResultFrame>
          <BackToLogin primary />
        </>
      )}
      {state === "invalid" && (
        <>
          <ResultFrame
            tone="warn"
            role="alert"
            testId="verify-invalid"
            title={t("verify.invalid.title")}
          >
            <Note>{t("verify.invalid.body")}</Note>
          </ResultFrame>
          <ResendForm {...resend} />
          <p style={{ margin: "20px 0 0", fontSize: 13 }}>
            <Link to="/login" style={{ color: "var(--accent)" }}>
              {t("links.login")}
            </Link>
          </p>
        </>
      )}
      {state === "unreachable" && (
        <>
          <ResultFrame
            tone="err"
            role="alert"
            testId="verify-unreachable"
            title={t("verify.unreachable.title")}
          >
            <Note>{t("verify.unreachable.body")}</Note>
          </ResultFrame>
          {onRetry && (
            <div style={{ marginTop: 18 }}>
              <Button
                variant="secondary"
                onClick={onRetry}
                style={{ width: "100%", justifyContent: "center" }}
              >
                {t("verify.unreachable.retry")}
              </Button>
            </div>
          )}
        </>
      )}
    </section>
  );
};
