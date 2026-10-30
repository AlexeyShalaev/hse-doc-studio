import { Save } from "lucide-react";
import { useTranslation } from "react-i18next";
import { Button, ResultFrame, Spinner } from "@shared/ui";
import { Notice } from "@shared/ui/ConflictKit";
import { failureKey, type Failure } from "../lib/failure";
import { ACTIONS } from "../lib/styles";
import { AllLockedNote } from "./parts";

/** Низ формы: отказ сервера, итог сохранения и кнопка. Если всё закрыто окружением, кнопки нет. */
export const SaveRow = ({
  testId,
  dirty,
  pending,
  failure,
  saved,
  allLocked,
}: {
  testId: string;
  dirty: boolean;
  pending: boolean;
  failure: Failure | null;
  saved: boolean;
  allLocked: boolean;
}) => {
  const { t } = useTranslation("adminInstall");
  return (
    <>
      {failure && (
        <Notice tone="err" role="alert" text={t(failureKey(failure.code))} />
      )}
      {saved && !failure && !dirty && (
        <ResultFrame
          tone="ok"
          role="status"
          testId={`${testId}-saved`}
          title={t("saved")}
        />
      )}
      {allLocked ? (
        <AllLockedNote />
      ) : (
        <div style={ACTIONS}>
          <Button
            type="submit"
            aria-disabled={!dirty || pending}
            style={{ gap: 8 }}
            data-testid={`${testId}-save`}
          >
            {pending ? (
              <Spinner size="sm" />
            ) : (
              <Save size={14} aria-hidden="true" />
            )}
            {pending ? t("saving") : t("save")}
          </Button>
        </div>
      )}
    </>
  );
};
