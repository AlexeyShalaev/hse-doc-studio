import { useMemo } from "react";
import { useSpace } from "./SpaceContext";
import { readSituation, type Situation } from "./situation";
import { useSpaceNav } from "./useSpaceNav";

export type SituationControls = Situation & {
  /** Задать условие; `null` возвращает умолчание версии. */
  setInput: (key: string, value: string | null) => void;
  /** Заменить все условия разом (например, условия готового случая). */
  setInputs: (inputs: Record<string, string>, caseId?: string | null) => void;
  setCase: (caseId: string | null) => void;
  /** Все условия по умолчанию, без готового случая. */
  reset: () => void;
};

/** Условия студента из адреса и запись обратно (pack-studio-ux.md, раздел 5.3). */
export const useSituation = (): SituationControls => {
  const { location } = useSpace();
  const nav = useSpaceNav();
  const state = useMemo(
    () => readSituation(location.search),
    [location.search],
  );
  return useMemo(
    () => ({
      ...state,
      setInput: (key, value) => {
        const rest = Object.entries(state.inputs).filter(
          ([name]) => name !== key,
        );
        nav.go({
          inputs: Object.fromEntries(
            value === null ? rest : [...rest, [key, value]],
          ),
        });
      },
      setInputs: (inputs, caseId) => {
        nav.go({ inputs, ...(caseId === undefined ? {} : { case: caseId }) });
      },
      setCase: (caseId) => {
        nav.go({ case: caseId });
      },
      reset: () => {
        nav.go({ inputs: {}, case: null });
      },
    }),
    [state, nav],
  );
};
