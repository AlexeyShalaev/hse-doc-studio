import { createContext, useCallback, useContext, useMemo } from "react";
import { useSearchParams } from "react-router";
import {
  OutcomeSectionSchema,
  OutcomeStateSchema,
  type OutcomeSection,
  type OutcomeState,
} from "@entities/pack-studio";

// Состояние экрана «Результат» живёт в адресе (template-studio-outcome.md, R10): ссылку можно
// отправить, перезагрузка возвращает тот же экран. Версия идёт в пути, остальное в query:
//   ?state=head&scenario=company-supervisor&i.kind=research&mode=student&selected=documents:report
// Вводные пишутся только как отличие от умолчаний. Всё из адреса проверяется: чужой или
// устаревший адрес даёт умолчания, а не поломанный экран.

export type OutcomeMode = "author" | "student";

/**
 * Что можно выбрать в центре: элементы разделов контракта и вводная из блока «Ветки» (у веток
 * в контракте раздела нет, они вне разделов результата, поэтому «branches» только у экрана).
 */
export type OutcomeSelection = {
  section: OutcomeSection | "branches";
  id: string;
};
export type OutcomeTab = "inputs" | "result" | "rules";

export type OutcomeUrlState = {
  /** Откуда считать: рабочее дерево (по умолчанию), последний коммит, база. */
  state: OutcomeState;
  scenario: string | null;
  /** Набор данных примера (`auto:normal`, `examples/ivanov`). */
  example: string | null;
  /** Вводные поверх сценария и умолчаний версии. */
  inputs: Record<string, string>;
  mode: OutcomeMode;
  /** Выбранный элемент результата: раздел и id (`documents:operator_manual`). */
  selected: OutcomeSelection | null;
  /** Вкладка телефона. */
  tab: OutcomeTab;
};

export const OUTCOME_DEFAULTS: OutcomeUrlState = {
  state: "work_tree",
  scenario: null,
  example: null,
  inputs: {},
  mode: "author",
  selected: null,
  tab: "result",
};

/** Те же пределы, что у сервера (раздел 4.6): до 64 вводных, значение до 128 знаков. */
export const MAX_INPUTS = 64;
export const MAX_INPUT_VALUE = 128;

const INPUT_PREFIX = "i.";
const INPUT_KEY = /^[a-z][a-z0-9_.-]{0,63}$/;
const SCENARIO = /^[A-Za-z0-9][A-Za-z0-9._-]{0,127}$/;
const EXAMPLE = /^[A-Za-z0-9][A-Za-z0-9_:./-]{0,254}$/;
const CONTROL = /\p{Cc}/u;

const MODES: readonly OutcomeMode[] = ["author", "student"];
const TABS: readonly OutcomeTab[] = ["inputs", "result", "rules"];

/** Разбор `раздел:id`; id может содержать двоеточие, делим по первому. */
export const parseSelected = (raw: string | null): OutcomeSelection | null => {
  if (!raw) return null;
  const cut = raw.indexOf(":");
  if (cut < 1) return null;
  const head = raw.slice(0, cut);
  const section =
    head === "branches"
      ? ({ success: true, data: "branches" } as const)
      : OutcomeSectionSchema.safeParse(head);
  const id = raw.slice(cut + 1);
  if (!section.success || id.length === 0 || id.length > 2000) return null;
  return { section: section.data, id };
};

export const formatSelected = (ref: OutcomeSelection): string =>
  `${ref.section}:${ref.id}`;

/** Состояние экрана из адреса: невалидное отбрасывается, пустое даёт умолчание. */
export const parseOutcomeSearch = (
  params: URLSearchParams,
): OutcomeUrlState => {
  const state = OutcomeStateSchema.safeParse(params.get("state"));
  const scenario = params.get("scenario");
  const example = params.get("example");
  const mode = params.get("mode");
  const tab = params.get("tab");
  const inputs: Record<string, string> = {};
  let count = 0;
  params.forEach((value, name) => {
    if (!name.startsWith(INPUT_PREFIX) || count >= MAX_INPUTS) return;
    const key = name.slice(INPUT_PREFIX.length);
    if (!INPUT_KEY.test(key) || key in inputs) return;
    if (
      value.length === 0 ||
      value.length > MAX_INPUT_VALUE ||
      CONTROL.test(value)
    ) {
      return;
    }
    inputs[key] = value;
    count += 1;
  });
  return {
    state: state.success ? state.data : OUTCOME_DEFAULTS.state,
    scenario: scenario && SCENARIO.test(scenario) ? scenario : null,
    example: example && EXAMPLE.test(example) ? example : null,
    inputs,
    mode: MODES.find((item) => item === mode) ?? OUTCOME_DEFAULTS.mode,
    selected: parseSelected(params.get("selected")),
    tab: TABS.find((item) => item === tab) ?? OUTCOME_DEFAULTS.tab,
  };
};

/**
 * Запись состояния в query: ставит только то, что отличается от умолчаний, остальное убирает.
 * Чужие параметры не трогает. `patch` накладывается на текущее состояние из `params`.
 */
export const writeOutcomeSearch = (
  params: URLSearchParams,
  patch: Partial<OutcomeUrlState>,
): URLSearchParams => {
  const next = { ...parseOutcomeSearch(params), ...patch };
  const out = new URLSearchParams(params);
  const put = (name: string, value: string | null, fallback: string | null) => {
    if (value === null || value === fallback) out.delete(name);
    else out.set(name, value);
  };
  put("state", next.state, OUTCOME_DEFAULTS.state);
  put("scenario", next.scenario, null);
  put("example", next.example, null);
  put("mode", next.mode, OUTCOME_DEFAULTS.mode);
  put("tab", next.tab, OUTCOME_DEFAULTS.tab);
  put("selected", next.selected ? formatSelected(next.selected) : null, null);
  for (const name of [...out.keys()]) {
    if (name.startsWith(INPUT_PREFIX)) out.delete(name);
  }
  for (const [key, value] of Object.entries(next.inputs).sort(([a], [b]) =>
    a < b ? -1 : a > b ? 1 : 0,
  )) {
    out.set(`${INPUT_PREFIX}${key}`, value);
  }
  return out;
};

/**
 * Подмена источника адреса: галерея состояний живёт внутри роутера приложения, а вложить второй
 * нельзя, поэтому у каждой записи свой «адрес» в памяти. В приложении контекста нет.
 */
export type OutcomeSearchSource = {
  search: string;
  set: (next: URLSearchParams) => void;
};
export const OutcomeSearchContext = createContext<OutcomeSearchSource | null>(
  null,
);

export type OutcomeUrlControls = {
  state: OutcomeUrlState;
  /** Изменить часть состояния; `push` добавляет запись в историю (по умолчанию замена). */
  update: (patch: Partial<OutcomeUrlState>, push?: boolean) => void;
};

/** Состояние экрана «Результат» из адреса и запись обратно. */
export const useOutcomeUrlState = (): OutcomeUrlControls => {
  const [params, setParams] = useSearchParams();
  const override = useContext(OutcomeSearchContext);
  const key = override ? override.search : params.toString();
  const state = useMemo(
    () => parseOutcomeSearch(new URLSearchParams(key)),
    [key],
  );
  const set = override?.set;
  const update = useCallback(
    (patch: Partial<OutcomeUrlState>, push = false) => {
      if (set) {
        set(writeOutcomeSearch(new URLSearchParams(key), patch));
        return;
      }
      setParams((prev) => writeOutcomeSearch(prev, patch), { replace: !push });
    },
    [key, set, setParams],
  );
  return { state, update };
};
