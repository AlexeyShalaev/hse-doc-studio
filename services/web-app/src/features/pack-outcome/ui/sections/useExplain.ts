import { useMemo } from "react";
import { useTranslation } from "react-i18next";
import type { PackOutcome } from "@entities/pack-studio";
import { makeExplainer, type Explainer } from "../../lib/explain";
import { useOutcomeModel } from "../../model";

/** Пересказ причин для секций: трасса из ответа, подписи вводных из `inputs`. */
export const useExplain = (outcome: PackOutcome): Explainer => {
  const { t, i18n } = useTranslation("packOutcome");
  const { inputs } = useOutcomeModel();
  const list = inputs.data?.inputs;
  const lang = i18n.language;
  return useMemo(
    () => makeExplainer(t, lang, outcome, list),
    [t, lang, outcome, list],
  );
};
