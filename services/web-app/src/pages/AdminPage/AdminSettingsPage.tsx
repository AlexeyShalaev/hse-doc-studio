import { useTranslation } from "react-i18next";
import { AdminAuthSettings } from "@features/admin-auth-settings";

/** Раздел «Настройки» админки: настройки входа и почты. */
export const AdminSettingsPage = () => {
  const { t } = useTranslation("adminSettings");
  return (
    <div
      className="flex flex-col"
      style={{ gap: 20 }}
      data-testid="admin-settings"
    >
      <header className="flex flex-col" style={{ gap: 4, maxWidth: 720 }}>
        <h1 style={{ margin: 0, fontSize: 20, fontWeight: 600 }}>
          {t("page.title")}
        </h1>
        <p style={{ margin: 0, fontSize: 13, color: "var(--fg-2)" }}>
          {t("page.lead")}
        </p>
      </header>
      <AdminAuthSettings />
    </div>
  );
};
