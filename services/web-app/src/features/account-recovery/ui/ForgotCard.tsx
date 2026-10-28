import { useId, useState, type FormEvent } from "react";
import { Link } from "react-router";
import { Mail } from "lucide-react";
import { useTranslation } from "react-i18next";
import { Button, Input, LinkDelivery, Spinner } from "@shared/ui";
import { ResultFrame } from "@shared/ui/ResultFrame";
import type { RecoveryFailure } from "../lib/recoveryErrors";
import { BackToLogin, FailureFrame, Heading, Lead, Note } from "./parts";

export type ForgotCardProps = {
  pending?: boolean;
  failure?: RecoveryFailure | null;
  onSubmit: (email: string) => void;
  initialEmail?: string;
};

/** Запрос ссылки для нового пароля: одно поле, ответ всегда одинаковый. */
export const ForgotCard = ({
  pending = false,
  failure = null,
  onSubmit,
  initialEmail = "",
}: ForgotCardProps) => {
  const { t } = useTranslation("auth");
  const uid = useId();
  const [email, setEmail] = useState(initialEmail);

  const submit = (event: FormEvent) => {
    event.preventDefault();
    if (pending || email.trim() === "") return;
    onSubmit(email.trim());
  };

  return (
    <section data-testid="auth-screen-forgot" aria-labelledby={`${uid}-title`}>
      <Heading id={`${uid}-title`}>{t("pages.forgot.title")}</Heading>
      <Lead>{t("pages.forgot.body")}</Lead>
      {failure && <FailureFrame failure={failure} testId="forgot-error" />}
      <form
        onSubmit={submit}
        className="flex flex-col"
        style={{ gap: 14 }}
        data-testid="forgot-form"
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
            <Mail size={15} aria-hidden="true" />
          )}
          {pending ? t("forgot.submitting") : t("forgot.submit")}
        </Button>
      </form>
      <p style={{ margin: "20px 0 0", fontSize: 13 }}>
        <Link to="/login" style={{ color: "var(--accent)" }}>
          {t("links.login")}
        </Link>
      </p>
    </section>
  );
};

/**
 * Итог запроса. Текст одинаков для любого адреса. Без SMTP письмо не уйдёт:
 * экран показывает ссылку, если сервер её отдал, и не гадает, если не отдал.
 */
export const ForgotSentCard = ({
  email,
  link,
  smtp,
}: {
  email: string;
  link: string | null;
  smtp: boolean;
}) => {
  const { t } = useTranslation("auth");
  return (
    <section data-testid="auth-screen-forgotSent" data-smtp={smtp}>
      <Heading>{t("pages.forgot.title")}</Heading>
      <div style={{ height: 12 }} />
      <ResultFrame
        tone="ok"
        role="status"
        testId="forgot-sent"
        title={t("forgot.sent.title")}
      >
        <Note>
          {smtp ? t("forgot.sent.body", { email }) : t("forgot.sent.noSmtp")}
        </Note>
      </ResultFrame>
      {link && (
        <div style={{ marginTop: 14 }}>
          <LinkDelivery kind="reset" link={link} once />
        </div>
      )}
      <BackToLogin />
    </section>
  );
};
