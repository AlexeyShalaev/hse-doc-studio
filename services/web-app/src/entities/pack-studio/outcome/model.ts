import { createContext, useContext } from "react";
import type { UseQueryResult } from "@tanstack/react-query";
import type {
  PackGit,
  PackOutcome,
  PackOutcomeInputs,
  PackOutcomeRequest,
  PackScenarioList,
  PackVersionRef,
  PackWorkspace,
} from "@entities/pack-studio";
import type {
  OutcomeMode,
  OutcomeTab,
  OutcomeSelection,
  OutcomeUrlControls,
} from "./urlState";

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

/** Вкладки телефона прежнего экрана «Результат»: поле модели, которое режим «Сравнить» не читает. */
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

/**
 * Всё, что нужно панелям и секциям экрана «Результат»: версия, состояние из адреса, запросы.
 * Срезы F2 (вводные), F3 и F4 (секции), F6 (правила) берут его из контекста и не ходят
 * в адрес и сервер сами: цепочка «адрес, запрос, отрисовка» собрана здесь один раз.
 */
export type OutcomeModel = {
  workspaceId: string;
  ref: PackVersionRef;
  /** Каталог версии от папки паков (`hse-cs-se/templates/vkr/versions/2026.1.2`): файлы правил лежат под ним. */
  versionPath: string;
  /** Выпущенная версия: правка отключена. */
  released: boolean;
  /** Телефон: колонки уступают место листам и вкладкам. */
  phone: boolean;
  url: OutcomeUrlControls;
  /**
   * Что показывать в центре: режим из адреса, но пока удерживается Alt в режиме «Как студент»,
   * временно «author». Адрес и переключатель в панели хранят выбранный режим, не этот.
   */
  view: OutcomeMode;
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
  select: (element: OutcomeSelection | null) => void;
  /**
   * Показать элемент: выбирает без переключения (повторный вызов выбор не снимает) и на телефоне
   * открывает вкладку «Почему?». Так работают «К документу» и переходы между секциями.
   */
  reveal: (element: OutcomeSelection) => void;
  /** Вкладки телефона и история браузера (на компьютере не используются). */
  nav: PhoneNav;
  highlight: OutcomeHighlight;
  /** Вид пространства: у папки без git нет веток и состояний `head` и `base`. */
  workspaceKind: PackWorkspace["kind"];
  /** Состояние git пространства (ветка, расхождение с базой); пока не пришло или без git пусто. */
  git: PackGit | undefined;
};

export const OutcomeModelContext = createContext<OutcomeModel | null>(null);

export const useOutcomeModel = (): OutcomeModel => {
  const model = useContext(OutcomeModelContext);
  if (!model) throw new Error("OutcomeModelContext is missing");
  return model;
};
