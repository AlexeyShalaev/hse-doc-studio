import { useTranslation } from "react-i18next";
import { AuthStubCard } from "@widgets/AuthLayout";

export const ResetPage = () => {
  const { t } = useTranslation("auth");
  return (
    <AuthStubCard
      screen="reset"
      links={[{ to: "/login", label: t("links.login") }]}
    />
  );
};
