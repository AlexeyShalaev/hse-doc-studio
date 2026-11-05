import { useTranslation } from "react-i18next";
import { Button } from "@shared/ui";
import { useRevokeAcceptance } from "../api/queries";

/** «Вернуть предупреждение»: снимает принятие, предупреждение снова считается. */
export const RevokeButton = ({
  check,
  variant = "secondary",
  testId,
}: {
  check: string;
  variant?: "secondary" | "ghost";
  testId?: string;
}) => {
  const { t } = useTranslation("adminDiagnostics");
  const revoke = useRevokeAcceptance();
  return (
    <Button
      type="button"
      size="sm"
      variant={variant}
      disabled={revoke.isPending}
      data-testid={testId ?? `diag-return-${check}`}
      onClick={() => {
        revoke.mutate(check);
      }}
    >
      {t("accepted.return")}
    </Button>
  );
};
