import { useTranslation } from "react-i18next";
import type { PackOutcome, PackOutcomeExplain } from "@entities/pack-studio";
import type { TraceText } from "../../lib/explain";
import { ElementState } from "./StateChip";

export type AppliedWhatIf = {
  input: string;
  value: string;
  /** Значение вводной в адресе до применения (его могло не быть). */
  previous: string | undefined;
};

type WhatIfProps = {
  counterfactuals: PackOutcomeExplain["counterfactuals"];
  text: TraceText;
  outcome: PackOutcome | undefined;
  applied: AppliedWhatIf | null;
  onApply: (input: string, value: string) => void;
  onRestore: () => void;
};

/**
 * «Что изменится, если...»: сервер пересчитал ядром каждую соседнюю вводную. Клик применяет ОДНУ
 * вводную через адрес экрана, результат пересчитывается; «Вернуть» ставит прежнее значение.
 */
export const WhatIf = ({
  counterfactuals,
  text,
  outcome,
  applied,
  onApply,
  onRestore,
}: WhatIfProps) => {
  const { t } = useTranslation("packOutcome");
  return (
    <section
      className="po-rules-block"
      aria-labelledby="po-whatif-title"
      data-testid="outcome-whatif"
    >
      <h3 className="po-rules-sub" id="po-whatif-title">
        {t("rules.whatIf.title")}
      </h3>
      {applied && (
        <div
          className="po-applied"
          role="status"
          data-testid="outcome-whatif-applied"
        >
          <span>
            {t("rules.whatIf.applied", {
              input: text.subject(applied.input),
              value: text.value(applied.input, applied.value),
            })}
          </span>
          <button
            type="button"
            className="btn sm"
            data-testid="outcome-whatif-restore"
            onClick={onRestore}
          >
            {t("rules.whatIf.restore")}
          </button>
        </div>
      )}
      {counterfactuals.length === 0 ? (
        <p className="po-note" data-testid="outcome-whatif-none">
          {t("rules.whatIf.none")}
        </p>
      ) : (
        <ul className="po-whatif">
          {counterfactuals.map((cf) => {
            const current = outcome?.inputs[cf.input];
            return (
              <li key={`${cf.input}=${cf.value}`}>
                <button
                  type="button"
                  className="po-whatif-btn"
                  data-testid={`outcome-whatif-${cf.input}-${cf.value}`}
                  onClick={() => {
                    onApply(cf.input, cf.value);
                  }}
                >
                  <span className="po-whatif-cond">
                    {t("rules.whatIf.if", {
                      input: text.subject(cf.input),
                      value: text.value(cf.input, cf.value),
                    })}
                    {current !== undefined && (
                      <span className="po-note">
                        {" "}
                        {t("rules.whatIf.current", {
                          value: text.value(cf.input, current),
                        })}
                      </span>
                    )}
                  </span>
                  <span className="po-whatif-then">
                    {t("rules.whatIf.then")}
                    <ElementState state={cf.result} />
                  </span>
                </button>
              </li>
            );
          })}
        </ul>
      )}
    </section>
  );
};
