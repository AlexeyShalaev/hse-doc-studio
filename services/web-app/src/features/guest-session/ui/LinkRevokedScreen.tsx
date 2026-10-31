import { useTranslation } from "react-i18next";
import { Link2Off } from "lucide-react";
import { Link } from "react-router";

/** Ссылку отозвали посреди работы (`link_inactive`): полноэкранное сообщение. */
export const LinkRevokedScreen = () => {
  const { t } = useTranslation("guest");
  return (
    <div
      role="alert"
      data-testid="link-revoked-screen"
      className="flex flex-col items-center justify-center"
      style={{
        flex: 1,
        gap: 12,
        padding: 32,
        textAlign: "center",
        minHeight: "60vh",
      }}
    >
      <Link2Off size={32} aria-hidden="true" style={{ color: "var(--fg-2)" }} />
      <h1 style={{ margin: 0, fontSize: 18, fontWeight: 600 }}>
        {t("revoked.title")}
      </h1>
      <p
        style={{
          margin: 0,
          color: "var(--fg-2)",
          fontSize: 13,
          maxWidth: 420,
          lineHeight: 1.5,
        }}
      >
        {t("revoked.text")}
      </p>
      <Link to="/" className="btn">
        {t("revoked.home")}
      </Link>
    </div>
  );
};
