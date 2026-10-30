import { useTranslation } from "react-i18next";
import { PageHeader } from "@shared/ui";
import { AdminAuthSettings } from "@features/admin-auth-settings";
import { useInstanceSettings } from "@features/admin-install";

/** Раздел «Вход и регистрация» админки: настройки входа и почты. */
export const AdminSettingsPage = () => {
  const { t } = useTranslation("adminSettings");
  const publicUrl = useInstanceSettings().data?.public_url;
  return (
    <div
      className="flex flex-col"
      style={{ gap: 20, flex: 1 }}
      data-testid="admin-settings"
    >
      <PageHeader title={t("page.title")} description={t("page.lead")} />
      <AdminAuthSettings publicUrl={publicUrl} />
    </div>
  );
};
