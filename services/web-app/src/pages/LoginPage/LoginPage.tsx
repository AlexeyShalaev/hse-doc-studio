import { useTranslation } from "react-i18next";
import { AuthStubCard } from "@widgets/AuthLayout";

export const LoginPage = () => {
  const { t } = useTranslation("auth");
  return (
    <AuthStubCard
      screen="login"
      links={[
        { to: "/register", label: t("links.register") },
        { to: "/forgot", label: t("links.forgot") },
      ]}
    />
  );
};
