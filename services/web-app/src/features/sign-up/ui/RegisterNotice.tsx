import { Link } from "react-router";
import { useTranslation } from "react-i18next";
import { ResultFrame } from "@shared/ui/ResultFrame";
import { Button, LinkDelivery } from "@shared/ui";

/** Регистрация недоступна: закрыта или нужна ссылка-приглашение. */
export const RegisterUnavailableCard = ({
  reason,
}: {
  reason: "closed" | "invite_required" | "invitation_invalid" | "unreachable";
}) => {
  const { t } = useTranslation("auth");
  return (
    <section data-testid="auth-screen-register" data-unavailable={reason}>
      <h1 style={{ fontSize: 20, fontWeight: 600, margin: "0 0 14px" }}>
        {t("pages.register.title")}
      </h1>
      <ResultFrame
        tone={
          reason === "closed"
            ? "info"
            : reason === "unreachable"
              ? "err"
              : "warn"
        }
        role="status"
        testId="register-unavailable"
        title={t(`register.unavailable.${reason}.title`)}
      >
        <p style={{ margin: 0, fontSize: 12.5, color: "var(--fg-2)" }}>
          {t(`register.unavailable.${reason}.body`)}
        </p>
      </ResultFrame>
      <div style={{ marginTop: 18 }}>
        <Button asChild style={{ width: "100%", justifyContent: "center" }}>
          <Link to="/login">{t("links.login")}</Link>
        </Button>
      </div>
    </section>
  );
};

/**
 * Итог регистрации. Ответ всегда нейтральный: «проверьте почту», без
 * признаков, занят ли адрес. Без SMTP письмо заменяет копируемая ссылка.
 */
export const RegisterResultCard = ({
  status,
  link,
  email,
}: {
  status: "check_email" | "pending_approval";
  link: string | null;
  email: string;
}) => {
  const { t } = useTranslation("auth");
  const variant =
    status === "check_email" && link ? "check_email_link" : status;
  return (
    <section data-testid="auth-screen-registerResult" data-status={status}>
      <h1 style={{ fontSize: 20, fontWeight: 600, margin: "0 0 14px" }}>
        {t("pages.register.title")}
      </h1>
      <ResultFrame
        tone={status === "pending_approval" ? "warn" : "ok"}
        role="status"
        testId="register-result"
        title={t(`register.result.${variant}.title`)}
      >
        <p style={{ margin: 0, fontSize: 12.5, color: "var(--fg-2)" }}>
          {t(`register.result.${variant}.body`, { email })}
        </p>
      </ResultFrame>
      {status === "check_email" && link && (
        <div style={{ marginTop: 14 }}>
          <LinkDelivery kind="verify" link={link} once />
        </div>
      )}
      <div style={{ marginTop: 18 }}>
        <Button
          asChild
          variant="secondary"
          style={{ width: "100%", justifyContent: "center" }}
        >
          <Link to="/login">{t("links.login")}</Link>
        </Button>
      </div>
    </section>
  );
};
