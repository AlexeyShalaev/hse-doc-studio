import { Lock, PencilLine } from "lucide-react";
import { useTranslation } from "react-i18next";
import { Badge } from "@shared/ui";

/** Состояние версии словом и значком (цвет не единственный признак): черновик или выпущена. */
export const VersionState = ({ released }: { released: boolean }) => {
  const { t } = useTranslation("packSpace");
  return released ? (
    <Badge data-testid="sp-state-released">
      <Lock size="0.6875rem" aria-hidden="true" />
      {t("nav.state.released")}
    </Badge>
  ) : (
    <Badge variant="warning" data-testid="sp-state-draft">
      <PencilLine size="0.6875rem" aria-hidden="true" />
      {t("nav.state.draft")}
    </Badge>
  );
};
