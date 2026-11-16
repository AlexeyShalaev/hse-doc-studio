import { useState } from "react";
import { useTranslation } from "react-i18next";
import { EmptyState } from "@shared/ui";
import { useOutcomeModel } from "../model";
import { EditBarSlot } from "./edit/lazy";
import { InputImpact } from "./rules/InputImpact";
import { WhyView } from "./rules/WhyView";
import type { AppliedWhatIf } from "./rules/WhatIf";
import "../rules.css";

/**
 * Панель «Правила и причины» (template-studio-outcome.md, 3.5, срез F6): контекстная, показывает
 * то, что выбрано в центре. У элемента результата это «Почему?» (цепочка правил, соседи, «что
 * если»), у вводной из блока «Ветки» или панели вводных её влияние. Над ними полоса правок
 * (срез F7): «Отменить», «Повторить», лента и сравнение результата до и после.
 */
export const RulesPanel = () => {
  const { t } = useTranslation("packOutcome");
  const { url, select } = useOutcomeModel();
  // «Что если» живёт выше выбора: вернуть вводную можно и после перехода к другому элементу.
  const [applied, setApplied] = useState<AppliedWhatIf | null>(null);
  const selected = url.state.selected;
  if (!selected) {
    return (
      <>
        <EditBarSlot />
        <EmptyState
          compact
          title={t("rules.emptyTitle")}
          description={t("rules.emptyLead")}
          testId="outcome-rules-empty"
        />
      </>
    );
  }
  const section = selected.section;
  return (
    <div className="po-rules" data-testid="outcome-rules">
      <EditBarSlot />
      {section === "branches" ? (
        <InputImpact key={selected.id} input={selected.id} />
      ) : (
        <WhyView
          key={`${section}:${selected.id}`}
          element={{ section, id: selected.id }}
          applied={applied}
          onApplied={setApplied}
        />
      )}
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
