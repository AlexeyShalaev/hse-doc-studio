import { Info } from "lucide-react";
import { useTranslation } from "react-i18next";
import { useOutcomeModel } from "../model";

/** Нижняя строка: «ничего не отправляется» и честные границы расчёта (`out_of_scope`). */
export const Footer = () => {
  const { t } = useTranslation("packOutcome");
  const { shown } = useOutcomeModel();
  const scope = shown?.out_of_scope ?? [];
  return (
    <footer className="po-footer" data-testid="outcome-footer">
      <Info size="0.8125rem" aria-hidden="true" />
      <span>{t("footer.note")}</span>
      {scope.length > 0 && (
        <span data-testid="outcome-out-of-scope">
          {t("footer.outOfScope", {
            items: scope.map((item) => t(`footer.scope.${item}`)).join(", "),
          })}
        </span>
      )}
    </footer>
  );
};
