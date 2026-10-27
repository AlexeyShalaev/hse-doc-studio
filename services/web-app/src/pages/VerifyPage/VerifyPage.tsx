import { useTranslation } from "react-i18next";
import { AuthStubCard } from "@widgets/AuthLayout";

export const VerifyPage = () => {
  const { t } = useTranslation("auth");
  return (
    <AuthStubCard
      screen="verify"
      links={[{ to: "/login", label: t("links.login") }]}
    />
  );
};
