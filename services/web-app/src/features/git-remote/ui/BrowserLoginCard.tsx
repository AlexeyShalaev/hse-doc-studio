import { LogIn } from "lucide-react";
import { useTranslation } from "react-i18next";

// Вход через браузер без токенов появится позже: карточка заметна, но выключена,
// чтобы было видно, куда движется продукт, и не вводило в заблуждение.
export const BrowserLoginCard = () => {
  const { t } = useTranslation("gitAccess");
  return (
    <div
      className="flex items-center"
      aria-disabled="true"
      title={t("browser.tooltip")}
      data-testid="browser-login-card"
      style={{
        gap: 10,
        padding: "9px 12px",
        borderRadius: "var(--r-2)",
        border: "1px dashed var(--border-strong)",
        opacity: 0.65,
        cursor: "not-allowed",
        fontSize: 12.5,
      }}
    >
      <LogIn size={14} aria-hidden="true" style={{ flexShrink: 0 }} />
      <span style={{ flex: 1, minWidth: 0 }}>
        <span style={{ display: "block", fontWeight: 600 }}>
          {t("browser.title")}
        </span>
        <span className="dim" style={{ display: "block", fontSize: 11 }}>
          {t("browser.text")}
        </span>
      </span>
      <span className="chip">{t("browser.soon")}</span>
    </div>
  );
};
