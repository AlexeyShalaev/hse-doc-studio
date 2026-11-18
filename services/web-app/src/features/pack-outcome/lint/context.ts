import { createContext, useContext } from "react";
import type { OutcomeElementRef, OutcomeRuleRef } from "@entities/pack-studio";
import type { Labeler } from "../ui/inputs/useLabeler";

/** Действия над находками и покрытием: ставят экран в нужное место, сами ничего не считают. */
export type LintActions = {
  labeler: Labeler;
  /** Значения свидетеля на экране «Результат» (вводные в адрес, режим «Результат»). */
  showCombination: (witness: Readonly<Record<string, string>>) => void;
  /** Элемент результата выбран и показан в «Почему?». */
  showElement: (element: OutcomeElementRef) => void;
  /** Файл и указатель находки в форме или исходнике; `false`, если файл вне версии. */
  openPlace: (file: string, pointer: string | null) => boolean;
  /** Правило покрытия в форме или исходнике; `false` у зашитых в движок правил. */
  openRule: (rule: OutcomeRuleRef) => boolean;
  /** Окно «Новый сценарий» с вводными свидетеля; `null`: с вводными экрана. */
  addScenario: (witness: Readonly<Record<string, string>> | null) => void;
  /** Можно писать сценарии (рабочее дерево, режим автора). */
  canAddScenario: boolean;
};

export const LintActionsContext = createContext<LintActions | null>(null);

export const useLintActions = (): LintActions => {
  const actions = useContext(LintActionsContext);
  if (!actions) throw new Error("LintActionsContext is missing");
  return actions;
};
