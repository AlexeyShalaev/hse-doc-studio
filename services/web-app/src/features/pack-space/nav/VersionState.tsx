import { CheckCheck, Lock, PencilLine } from "lucide-react";
import { useTranslation } from "react-i18next";
import { Badge } from "@shared/ui";

/**
 * Состояние версии словом и значком (цвет не единственный признак): черновик, выпущена или принята
 * (запрос с ней слит, а пространство ещё не обновляли).
 */
export const VersionState = ({
  released,
  accepted = false,
}: {
  released: boolean;
  accepted?: boolean | undefined;
}) => {
  const { t } = useTranslation("packSpace");
  if (released) {
    return (
      <Badge data-testid="sp-state-released">
        <Lock size="0.6875rem" aria-hidden="true" />
        {t("nav.state.released")}
      </Badge>
    );
  }
  return accepted ? (
    <Badge variant="success" data-testid="sp-state-accepted">
      <CheckCheck size="0.6875rem" aria-hidden="true" />
      {t("nav.state.accepted")}
    </Badge>
  ) : (
    <Badge variant="warning" data-testid="sp-state-draft">
      <PencilLine size="0.6875rem" aria-hidden="true" />
      {t("nav.state.draft")}
    </Badge>
  );
};
