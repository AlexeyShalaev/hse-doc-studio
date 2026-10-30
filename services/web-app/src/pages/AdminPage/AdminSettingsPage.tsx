import { useTranslation } from "react-i18next";
import { PageHeader } from "@shared/ui";
import { AdminAuthSettings } from "@features/admin-auth-settings";

/** Раздел «Вход и регистрация» админки: настройки входа и почты. */
export const AdminSettingsPage = () => {
  const { t } = useTranslation("adminSettings");
  return (
    <div
      className="flex flex-col"
      style={{ gap: 20, flex: 1 }}
      data-testid="admin-settings"
    >
      <PageHeader title={t("page.title")} description={t("page.lead")} />
      <AdminAuthSettings />
    </div>
  );
};
