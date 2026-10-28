import { Link, useSearchParams } from "react-router";
import { useTranslation } from "react-i18next";
import { Button } from "@shared/ui";
import { ResultFrame } from "@shared/ui/ResultFrame";
import {
  authErrorTone,
  normalizeAuthErrorCode,
  type AuthErrorCode,
} from "../lib/authErrorCodes";

export type AuthErrorCardProps = { code: AuthErrorCode | "unknown" };

/** Внешний вход не завершился: причина по коду и путь назад ко входу. */
export const AuthErrorCard = ({ code }: AuthErrorCardProps) => {
  const { t } = useTranslation("auth");
  return (
    <section data-testid="auth-screen-authError" data-code={code}>
      <h1 style={{ fontSize: 20, fontWeight: 600, margin: "0 0 14px" }}>
        {t("pages.authError.title")}
      </h1>
      <ResultFrame
        tone={authErrorTone(code)}
        role="alert"
        testId="auth-error-frame"
        title={t(`authError.codes.${code}.title`)}
      >
        <p style={{ margin: 0, fontSize: 12.5, color: "var(--fg-2)" }}>
          {t(`authError.codes.${code}.body`)}
        </p>
      </ResultFrame>
      <div style={{ marginTop: 18 }}>
        <Button asChild style={{ width: "100%", justifyContent: "center" }}>
          <Link to="/login" style={{ textDecoration: "none" }}>
            {t("links.login")}
          </Link>
        </Button>
      </div>
    </section>
  );
};

export const AuthErrorFromUrl = () => {
  const [params] = useSearchParams();
  return <AuthErrorCard code={normalizeAuthErrorCode(params.get("code"))} />;
};
