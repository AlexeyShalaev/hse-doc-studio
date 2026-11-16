import { useTranslation } from "react-i18next";
import { EmptyState } from "@shared/ui";
import { useOutcomeModel } from "../model";

/**
 * Панель «Правила и причины». Каркас (срез F1): показывает выбранный элемент из адреса и
 * снимает выбор. Цепочка «Почему?», «что ещё решает правило», «что если» и правка по месту
 * приходят срезами F6 и F7.
 */
export const RulesPanel = () => {
  const { t } = useTranslation("packOutcome");
  const { url, select } = useOutcomeModel();
  const selected = url.state.selected;
  if (!selected) {
    return (
      <EmptyState
        compact
        title={t("rules.emptyTitle")}
        description={t("rules.emptyLead")}
        testId="outcome-rules-empty"
      />
    );
  }
  return (
    <div className="po-rules" data-testid="outcome-rules">
      <p className="po-rules-label">{t("rules.selected")}</p>
      <p className="po-rules-element" data-testid="outcome-selected">
        <span className="ps-mark">{t(`sections.${selected.section}`)}</span>
        <span className="mono po-rules-id">{selected.id}</span>
      </p>
      <p className="po-stub">{t("rules.pending")}</p>
      <button
        type="button"
        className="btn sm"
        data-testid="outcome-selected-clear"
        onClick={() => {
          select(null);
        }}
      >
        {t("rules.clear")}
      </button>
    </div>
  );
};
