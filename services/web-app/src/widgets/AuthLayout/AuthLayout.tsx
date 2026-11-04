import { Outlet, useLocation } from "react-router";
import { useTranslation } from "react-i18next";
import { useBootstrap } from "@entities/session";
import { AuthSwitches } from "./AuthSwitches";

const Logomark = () => (
  <div
    className="flex items-center justify-center font-mono shrink-0"
    aria-hidden
    style={{
      width: 32,
      height: 32,
      borderRadius: 8,
      background: "linear-gradient(135deg, var(--accent), var(--accent))",
      color: "var(--accent-ink)",
      fontWeight: 700,
      fontSize: 15,
      boxShadow: "0 0 0 1px var(--accent-line)",
    }}
  >
    §
  </div>
);

/**
 * Каркас экранов без сессии (вход, регистрация, сброс пароля, мастер первого
 * запуска): центрированная карточка, логотип, язык и тема, версия. Без
 * титлбара, баннера Docker, проверок запуска и агента: человек ещё не вошёл.
 */
export const AuthLayout = () => {
  const { t } = useTranslation("auth");
  const { data } = useBootstrap();
  const version = data?.version ?? "";
  // Мастеру первого запуска нужна ширина под степпер с подписями.
  const wide = useLocation().pathname.replace(/\/$/, "") === "/first-run";

  return (
    <div
      data-testid="auth-layout"
      className="flex flex-col flex-1 min-h-0"
      style={{ background: "var(--bg-0)", color: "var(--fg-0)" }}
    >
      <header className="auth-header flex items-center justify-between">
        <div className="flex items-center" style={{ gap: 10 }}>
          <Logomark />
          <span style={{ fontWeight: 600, fontSize: 14 }}>
            {t("layout.product")}
          </span>
        </div>
        <AuthSwitches />
      </header>
      <main className="auth-main flex flex-1 items-center justify-center">
        <div className="auth-card" style={{ maxWidth: wide ? 600 : 420 }}>
          <Outlet />
        </div>
      </main>
      {version !== "" && (
        <footer
          className="mono"
          data-testid="auth-layout-version"
          style={{
            padding: "10px 24px",
            fontSize: 11,
            color: "var(--fg-3)",
            textAlign: "center",
          }}
        >
          {t("layout.version", { version })}
        </footer>
      )}
    </div>
  );
};
