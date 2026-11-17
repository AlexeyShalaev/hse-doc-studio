import { useCallback } from "react";
import { useLocation, useNavigate } from "react-router";
import {
  writeOutcomeSearch,
  type OutcomeTab,
  type OutcomeUrlControls,
  type OutcomeUrlState,
} from "./urlState";

// Вкладки телефона (template-studio-outcome.md, 3.12): «Результат» и «Почему?» это страницы,
// «Вводные» лист поверх одной из них. Вкладка живёт в адресе (`tab`), а «Назад» браузера читает её
// как историю: открытие листа добавляет запись, «Назад» закрывает лист и возвращает страницу под ним.

/** Метка записи, которую телефон добавил при открытии листа «Вводные». */
type SheetMark = {
  poNav: true;
  /** Адрес без вкладки на момент открытия: по нему видно, менялось ли что-то внутри листа. */
  base: string;
  /** Страница под листом. */
  main: Exclude<OutcomeTab, "inputs">;
};

const isMark = (value: unknown): value is SheetMark => {
  if (typeof value !== "object" || value === null) return false;
  const mark = value as Partial<SheetMark>;
  return mark.poNav === true && typeof mark.base === "string";
};

/** Адрес без вкладки в каноническом виде: сравнивается с меткой при закрытии листа. */
const baseOf = (state: OutcomeUrlState): string =>
  writeOutcomeSearch(new URLSearchParams(), {
    ...state,
    tab: "result",
  }).toString();

export type PhoneNav = {
  /** Вкладка с учётом режима: в «Как студент» «Почему?» нет. */
  tab: OutcomeTab;
  /** Страница под листом «Вводные» (или сама вкладка, если лист закрыт). */
  main: Exclude<OutcomeTab, "inputs">;
  /** Перейти на вкладку. «Почему?» добавляет запись в историю: «Назад» вернёт «Результат». */
  go: (tab: OutcomeTab) => void;
  /** Закрыть лист «Вводные». Если внутри ничего не меняли, это шаг «Назад» по истории. */
  closeSheet: () => void;
};

/** Вкладки телефона поверх адреса и истории браузера. */
export const usePhoneNav = (
  url: OutcomeUrlControls,
  student: boolean,
): PhoneNav => {
  const navigate = useNavigate();
  const here: unknown = useLocation().state;
  const { state, update } = url;
  const tab: OutcomeTab =
    student && state.tab === "rules" ? "result" : state.tab;
  const main: Exclude<OutcomeTab, "inputs"> =
    tab !== "inputs" ? tab : isMark(here) ? here.main : "result";

  const closeSheet = useCallback(() => {
    if (isMark(here) && here.base === baseOf(state)) {
      void navigate(-1);
      return;
    }
    update({ tab: main });
  }, [here, main, navigate, state, update]);

  const go = useCallback(
    (to: OutcomeTab) => {
      if (to === tab) {
        if (to === "inputs") closeSheet();
        return;
      }
      if (to === "inputs") {
        const mark: SheetMark = {
          poNav: true,
          base: baseOf(state),
          main: tab === "rules" ? "rules" : "result",
        };
        update({ tab: "inputs" }, true, mark);
        return;
      }
      if (tab === "inputs") {
        if (to === main) closeSheet();
        else update({ tab: to });
        return;
      }
      update({ tab: to }, to === "rules");
    },
    [closeSheet, main, state, tab, update],
  );

  return { tab, main, go, closeSheet };
};
