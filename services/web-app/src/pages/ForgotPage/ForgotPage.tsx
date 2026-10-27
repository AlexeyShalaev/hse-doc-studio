import { useTranslation } from "react-i18next";
import { AuthStubCard } from "@widgets/AuthLayout";

export const ForgotPage = () => {
  const { t } = useTranslation("auth");
  return (
    <AuthStubCard
      screen="forgot"
      links={[{ to: "/login", label: t("links.login") }]}
    />
  );
};
