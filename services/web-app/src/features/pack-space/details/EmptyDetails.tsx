import { SlidersHorizontal } from "lucide-react";
import { useTranslation } from "react-i18next";
import { EditDelta } from "./EditFeedback";
import type { ConditionEdit } from "./edit/useConditionEdit";

/** Ничего не выбрано (pack-studio-ux.md, 5.4, состояние 1): что здесь можно сделать. */
export const EmptyDetails = ({ edit }: { edit: ConditionEdit }) => {
  const { t } = useTranslation("packSpace");
  return (
    <div className="sp-details" data-testid="sp-details-empty">
      <span className="sp-details-kicker">{t("details.empty.kicker")}</span>
      <h3 className="sp-details-title">{t("details.empty.title")}</h3>
      <p className="sp-details-muted">{t("details.empty.lead")}</p>
      <div className="sp-details-card">
        <p className="sp-details-card-title">
          <SlidersHorizontal size="0.9375rem" aria-hidden="true" />
          {t("details.empty.cardTitle")}
        </p>
        <p className="sp-details-muted">{t("details.empty.cardLead")}</p>
      </div>
      <EditDelta edit={edit} />
    </div>
  );
};
