import { useEffect, useState } from "react";
import { useTranslation } from "react-i18next";
import { Button } from "@shared/ui";
import { useDiagnosticsQuiet } from "../api/queries";
import { acceptableCheck } from "../lib/acceptance";
import { ensureAdminDiagnosticsLocales } from "../lib/locales";
import { AcceptDialog } from "./AcceptDialog";

/**
 * Кнопка «Принимаю: не делаю сознательно» для баннеров на других страницах админки.
 * Показывается, только пока предупреждение этой проверки можно принять.
 */
export const AcceptWarningButton = ({ check }: { check: string }) => {
  const { t } = useTranslation("adminDiagnostics");
  const data = useDiagnosticsQuiet().data;
  const [open, setOpen] = useState(false);
  const [ready, setReady] = useState(false);
  useEffect(() => {
    void ensureAdminDiagnosticsLocales().then(() => {
      setReady(true);
    });
  }, []);
  if (!ready || !acceptableCheck(data, check)) return null;
  return (
    <>
      <Button
        type="button"
        size="sm"
        variant="secondary"
        data-testid={`diag-accept-${check}`}
        onClick={() => {
          setOpen(true);
        }}
      >
        {t("accept.button")}
      </Button>
      {open && (
        <AcceptDialog
          check={check}
          onClose={() => {
            setOpen(false);
          }}
        />
      )}
    </>
  );
};
