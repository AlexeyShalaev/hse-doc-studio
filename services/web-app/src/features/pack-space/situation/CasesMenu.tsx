import { useState } from "react";
import { Check, ChevronDown } from "lucide-react";
import { useTranslation } from "react-i18next";
import { Popover, PopoverContent, PopoverTrigger } from "@shared/ui/Popover";
import type { SituationModel } from "./useSituationModel";

/**
 * «Готовые случаи»: сохранённые ситуации. Точка у случая зелёная, когда ожидаемый результат
 * совпал, оранжевая, когда «поехал». Выбор ставит условия случая на полосу.
 */
export const CasesMenu = ({ model }: { model: SituationModel }) => {
  const { t } = useTranslation("packSpace");
  const [open, setOpen] = useState(false);
  const { cases, caseId } = model;
  const picked = caseId === null ? null : model.caseName(caseId);
  const pick = (id: string | null) => {
    setOpen(false);
    if (id !== caseId) model.pickCase(id);
  };
  return (
    <Popover open={open} onOpenChange={setOpen}>
      <PopoverTrigger asChild>
        <button
          type="button"
          className="btn sm sp-cases-btn"
          data-active={picked === null ? undefined : "true"}
          data-testid="sp-sit-cases"
        >
          <span className="sp-cases-name">
            {picked ?? t("situation.cases.title")}
          </span>
          <ChevronDown size="0.75rem" aria-hidden="true" />
        </button>
      </PopoverTrigger>
      <PopoverContent
        width={340}
        align="end"
        aria-label={t("situation.cases.title")}
      >
        <div className="sp-sit-pop">
          {cases.length === 0 ? (
            <p className="sp-sit-pop-note" data-testid="sp-sit-cases-empty">
              {t("situation.cases.empty")}
            </p>
          ) : (
            <div
              role="radiogroup"
              aria-label={t("situation.cases.title")}
              className="sp-sit-list"
            >
              <button
                type="button"
                role="radio"
                className="sp-sit-option"
                aria-checked={caseId === null}
                data-testid="sp-sit-case-none"
                onClick={() => {
                  pick(null);
                }}
              >
                {t("situation.cases.none")}
                {caseId === null ? <Check size="0.875rem" /> : null}
              </button>
              {cases.map((entry) => {
                const badge = model.badge(entry);
                return (
                  <button
                    key={entry.id}
                    type="button"
                    role="radio"
                    className="sp-sit-option"
                    aria-checked={entry.id === caseId}
                    disabled={entry.error !== null && entry.id !== caseId}
                    data-testid={`sp-sit-case-${entry.id}`}
                    onClick={() => {
                      pick(entry.id);
                    }}
                  >
                    <span className="sp-case-dot" data-badge={badge} />
                    <span className="sp-case-name">
                      {model.caseName(entry.id)}
                    </span>
                    <span className="sp-case-state">
                      {t(`situation.cases.badge.${badge}`)}
                    </span>
                  </button>
                );
              })}
            </div>
          )}
        </div>
      </PopoverContent>
    </Popover>
  );
};
