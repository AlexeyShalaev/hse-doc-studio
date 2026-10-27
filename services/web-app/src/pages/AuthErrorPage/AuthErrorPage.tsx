import { useTranslation } from "react-i18next";
import { AuthStubCard } from "@widgets/AuthLayout";

export const AuthErrorPage = () => {
  const { t } = useTranslation("auth");
  return (
    <AuthStubCard
      screen="authError"
      links={[{ to: "/login", label: t("links.login") }]}
    />
  );
};
