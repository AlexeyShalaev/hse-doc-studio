import { useTranslation } from "react-i18next";
import { AuthStubCard } from "@widgets/AuthLayout";

export const InvitePage = () => {
  const { t } = useTranslation("auth");
  return (
    <AuthStubCard
      screen="invite"
      links={[{ to: "/login", label: t("links.login") }]}
    />
  );
};
