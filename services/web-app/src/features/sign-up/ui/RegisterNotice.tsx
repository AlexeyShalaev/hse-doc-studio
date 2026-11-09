import { Link } from "react-router";
import { useTranslation } from "react-i18next";
import { ResultFrame } from "@shared/ui/ResultFrame";
import { Button, LinkDelivery } from "@shared/ui";

/** Регистрация недоступна: закрыта или нужна ссылка-приглашение. */
export const RegisterUnavailableCard = ({
  reason,
}: {
  reason:
    | "closed"
    | "invite_required"
    | "smtp_required"
    | "invitation_invalid"
    | "unreachable";
}) => {
  const { t } = useTranslation("auth");
  return (
    <section data-testid="auth-screen-register" data-unavailable={reason}>
      <h1
        style={{ fontSize: "1.25rem", fontWeight: 600, margin: "0 0 0.875rem" }}
      >
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
        <p style={{ margin: 0, fontSize: "0.78125rem", color: "var(--fg-2)" }}>
          {t(`register.unavailable.${reason}.body`)}
        </p>
      </ResultFrame>
      <div style={{ marginTop: "1.125rem" }}>
        <Button asChild style={{ width: "100%", justifyContent: "center" }}>
          <Link to="/login" style={{ textDecoration: "none" }}>
            {t("links.login")}
          </Link>
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
  invited = false,
  next = "",
}: {
  status: "check_email" | "pending_approval";
  link: string | null;
  email: string;
  // Приглашение на этот адрес само подтвердило почту: аккаунт готов, письма ждать не надо.
  invited?: boolean;
  /** Куда вернуться после входа (проверенный путь); пусто: как обычно. */
  next?: string;
}) => {
  const { t } = useTranslation("auth");
  const variant =
    status === "check_email" && invited
      ? "invited"
      : status === "check_email" && link
        ? "check_email_link"
        : status;
  return (
    <section data-testid="auth-screen-registerResult" data-status={status}>
      <h1
        style={{ fontSize: "1.25rem", fontWeight: 600, margin: "0 0 0.875rem" }}
      >
        {t("pages.register.title")}
      </h1>
      <ResultFrame
        tone={status === "pending_approval" ? "warn" : "ok"}
        role="status"
        testId="register-result"
        title={t(`register.result.${variant}.title`)}
      >
        <p style={{ margin: 0, fontSize: "0.78125rem", color: "var(--fg-2)" }}>
          {t(`register.result.${variant}.body`, { email })}
        </p>
      </ResultFrame>
      {status === "check_email" && link && (
        <div style={{ marginTop: "0.875rem" }}>
          <LinkDelivery kind="verify" link={link} once />
        </div>
      )}
      <div style={{ marginTop: "1.125rem" }}>
        <Button
          asChild
          variant="secondary"
          style={{ width: "100%", justifyContent: "center" }}
        >
          <Link
            to={next ? `/login?next=${encodeURIComponent(next)}` : "/login"}
          >
            {t("links.login")}
          </Link>
        </Button>
      </div>
    </section>
  );
};
