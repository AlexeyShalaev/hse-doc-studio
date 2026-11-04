import { Lock } from "lucide-react";
import { useTranslation } from "react-i18next";

/** Низ раздела, где всё задано окружением: один замок вместо замка в каждой строке. */
export const AllLockedNote = () => {
  const { t } = useTranslation("adminSettings");
  return (
    <span className="adm-field-note" data-testid="all-locked-note">
      <Lock size="0.75rem" aria-hidden="true" />
      {t("locked.note")}
    </span>
  );
};
