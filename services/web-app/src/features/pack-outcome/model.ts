import { createContext, useContext } from "react";
import type { UseQueryResult } from "@tanstack/react-query";
import type {
  OutcomeElementRef,
  PackOutcome,
  PackOutcomeInputs,
  PackOutcomeRequest,
  PackScenarioList,
  PackVersionRef,
} from "@entities/pack-studio";
import type { OutcomeUrlControls } from "./lib/urlState";

/**
 * Подсветка элементов результата, связанных с вводной (клик по вводной в левой панели). Связи
 * берутся из трассы ответа, секции спрашивают `isHighlighted` и красят элемент у себя.
 */
export type OutcomeHighlight = {
  /** Вводная, чьи связи подсвечены. */
  input: string | null;
  /** Ключи `раздел:id` элементов результата. */
  elements: ReadonlySet<string>;
  setInput: (id: string | null) => void;
};

export const isHighlighted = (
  highlight: OutcomeHighlight,
  element: OutcomeElementRef,
): boolean => highlight.elements.has(`${element.section}:${element.id}`);

/**
 * Всё, что нужно панелям и секциям экрана «Результат»: версия, состояние из адреса, запросы.
 * Срезы F2 (вводные), F3 и F4 (секции), F6 (правила) берут его из контекста и не ходят
 * в адрес и сервер сами: цепочка «адрес, запрос, отрисовка» собрана здесь один раз.
 */
export type OutcomeModel = {
  workspaceId: string;
  ref: PackVersionRef;
  /** Выпущенная версия: правка отключена. */
  released: boolean;
  /** Телефон: колонки уступают место листам и вкладкам. */
  phone: boolean;
  url: OutcomeUrlControls;
  /** Запрос расчёта, собранный из адреса. */
  request: PackOutcomeRequest;
  /** Ответ расчёта; при пересчёте остаётся прежний (`isPlaceholderData`). */
  outcome: UseQueryResult<PackOutcome>;
  /** Результат для показа: свежий либо прежний после неудачного пересчёта. */
  shown: PackOutcome | undefined;
  /** Показан не последний расчёт: пересчёт идёт или не удался. */
  stale: boolean;
  inputs: UseQueryResult<PackOutcomeInputs>;
  scenarios: UseQueryResult<PackScenarioList>;
  select: (element: OutcomeElementRef | null) => void;
  highlight: OutcomeHighlight;
};

export const OutcomeModelContext = createContext<OutcomeModel | null>(null);

export const useOutcomeModel = (): OutcomeModel => {
  const model = useContext(OutcomeModelContext);
  if (!model) throw new Error("OutcomeModelContext is missing");
  return model;
};
