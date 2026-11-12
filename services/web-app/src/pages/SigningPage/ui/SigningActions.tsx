import type { ReactNode } from "react";
import { useTranslation } from "react-i18next";
import { Check, Undo2 } from "lucide-react";
import { Button } from "@shared/ui";
import {
  canReturnForRework,
  type SigningTask,
  type SigningTaskAction,
} from "@entities/signing-route";
import { approveBlocker } from "../lib/signingState";

export type SigningActionsProps = {
  task: SigningTask;
  action: SigningTaskAction;
  busy: boolean;
  /** Идёт именно согласование: подпись кнопки «Согласуем…». */
  approving?: boolean;
  /** Главная кнопка блока подписи (W5); без неё «Согласовать» для `approve`. */
  primary?: ReactNode;
  onApprove: () => void;
  onReturn: () => void;
};

/** Кнопки по ситуации (раздел 4.4): «Согласовать» и рядом «Вернуть на доработку». */
export const SigningActions = ({
  task,
  action,
  busy,
  approving = false,
  primary,
  onApprove,
  onReturn,
}: SigningActionsProps) => {
  const { t } = useTranslation("signing");
  const blocker = action === "approve" ? approveBlocker(task.me) : null;
  const main =
    primary ??
    (action === "approve" ? (
      <Button
        type="button"
        disabled={busy || blocker !== null}
        onClick={onApprove}
        data-testid="signing-approve"
      >
        <Check size="0.875rem" aria-hidden />
        {approving ? t("actions.approving") : t("actions.approve")}
      </Button>
    ) : null);
  return (
    <div className="sgn-actions" data-testid="signing-actions">
      {main}
      {canReturnForRework(task.me.state) && (
        <Button
          type="button"
          variant="secondary"
          disabled={busy}
          onClick={onReturn}
          data-testid="signing-return"
        >
          <Undo2 size="0.875rem" aria-hidden />
          {t("actions.return")}
        </Button>
      )}
      {blocker && primary == null && (
        <p className="sgn-hint" data-testid="signing-approve-blocked">
          {t(`failure.${blocker}_required`)}
        </p>
      )}
    </div>
  );
};
