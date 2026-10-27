import { useTranslation } from "react-i18next";
import { AuthStubCard } from "@widgets/AuthLayout";

export const RegisterPage = () => {
  const { t } = useTranslation("auth");
  return (
    <AuthStubCard
      screen="register"
      links={[{ to: "/login", label: t("links.login") }]}
    />
  );
};
