import { createContext, useCallback, useContext, useMemo } from "react";
import { useLocation, useSearchParams } from "react-router";
import { formatSide, parseSide, type CompareSide } from "./compareSide";
import {
  OutcomeSectionSchema,
  OutcomeStateSchema,
  type OutcomeSection,
  type OutcomeState,
} from "@entities/pack-studio";

// Состояние экрана «Результат» живёт в адресе (template-studio-outcome.md, R10): ссылку можно
// отправить, перезагрузка возвращает тот же экран. Версия идёт в пути, остальное в query:
//   ?state=head&scenario=company-supervisor&i.kind=research&mode=student&selected=documents:report
// Режимы центра (срез F9): `view=matrix|atlas|compare` (результат это умолчание), закрепления атласа
// `p.<вводная>=<значение>`, `against=base` у матрицы, стороны сравнения `left` и `right`.
// Вводные пишутся только как отличие от умолчаний. Всё из адреса проверяется: чужой или
// устаревший адрес даёт умолчания, а не поломанный экран.

export type OutcomeMode = "author" | "student";

/** Режим центра: результат, матрица сценариев, атлас комбинаций, сравнение двух сторон, проверка пака (линтер, срез F11). */
export type OutcomeView = "result" | "matrix" | "atlas" | "compare" | "lint";
export const OUTCOME_VIEWS: readonly OutcomeView[] = [
  "result",
  "matrix",
  "atlas",
  "compare",
  "lint",
];

/** С чем матрица сверяет клетки: с ожиданиями сценария или с базой (`against: base`). */
export type MatrixAgainst = "expected" | "base";

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
  /** Режим центра (срез F9). */
  view: OutcomeView;
  /** Закреплённые вводные атласа: режут таблицу, остаются в измерениях с одним значением. */
  pin: Record<string, string>;
  against: MatrixAgainst;
  /** Стороны сравнения; `null`: экран берёт умолчание по числу сценариев и вид пространства. */
  left: CompareSide | null;
  right: CompareSide | null;
};

export const OUTCOME_DEFAULTS: OutcomeUrlState = {
  state: "work_tree",
  scenario: null,
  example: null,
  inputs: {},
  mode: "author",
  selected: null,
  tab: "result",
  view: "result",
  pin: {},
  against: "expected",
  left: null,
  right: null,
};

/** Те же пределы, что у сервера (раздел 4.6): до 64 вводных, значение до 128 знаков. */
export const MAX_INPUTS = 64;
export const MAX_INPUT_VALUE = 128;

const INPUT_PREFIX = "i.";
const PIN_PREFIX = "p.";
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

/** Вводные под префиксом (`i.` или `p.`): невалидное и лишнее сверх предела отбрасывается. */
const readInputs = (
  params: URLSearchParams,
  prefix: string,
): Record<string, string> => {
  const out: Record<string, string> = {};
  let count = 0;
  params.forEach((value, name) => {
    if (!name.startsWith(prefix) || count >= MAX_INPUTS) return;
    const key = name.slice(prefix.length);
    if (!INPUT_KEY.test(key) || key in out) return;
    if (
      value.length === 0 ||
      value.length > MAX_INPUT_VALUE ||
      CONTROL.test(value)
    ) {
      return;
    }
    out[key] = value;
    count += 1;
  });
  return out;
};

/** Состояние экрана из адреса: невалидное отбрасывается, пустое даёт умолчание. */
export const parseOutcomeSearch = (
  params: URLSearchParams,
): OutcomeUrlState => {
  const state = OutcomeStateSchema.safeParse(params.get("state"));
  const scenario = params.get("scenario");
  const example = params.get("example");
  const mode = params.get("mode");
  const tab = params.get("tab");
  const inputs = readInputs(params, INPUT_PREFIX);
  const pin = readInputs(params, PIN_PREFIX);
  return {
    state: state.success ? state.data : OUTCOME_DEFAULTS.state,
    scenario: scenario && SCENARIO.test(scenario) ? scenario : null,
    example: example && EXAMPLE.test(example) ? example : null,
    inputs,
    mode: MODES.find((item) => item === mode) ?? OUTCOME_DEFAULTS.mode,
    selected: parseSelected(params.get("selected")),
    tab: TABS.find((item) => item === tab) ?? OUTCOME_DEFAULTS.tab,
    view:
      OUTCOME_VIEWS.find((item) => item === params.get("view")) ??
      OUTCOME_DEFAULTS.view,
    pin,
    against: params.get("against") === "base" ? "base" : "expected",
    left: parseSide(params.get("left")),
    right: parseSide(params.get("right")),
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
  put("view", next.view, OUTCOME_DEFAULTS.view);
  put("against", next.against, OUTCOME_DEFAULTS.against);
  put("left", next.left ? formatSide(next.left) : null, null);
  put("right", next.right ? formatSide(next.right) : null, null);
  put("selected", next.selected ? formatSelected(next.selected) : null, null);
  for (const name of [...out.keys()]) {
    if (name.startsWith(INPUT_PREFIX) || name.startsWith(PIN_PREFIX)) {
      out.delete(name);
    }
  }
  for (const [prefix, values] of [
    [INPUT_PREFIX, next.inputs],
    [PIN_PREFIX, next.pin],
  ] as const) {
    for (const [key, value] of Object.entries(values).sort(([a], [b]) =>
      a < b ? -1 : a > b ? 1 : 0,
    )) {
      out.set(`${prefix}${key}`, value);
    }
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

// Счётчик записей в адрес экрана. Лист на телефоне по нему узнаёт, менялся ли адрес, пока он был
// открыт: состояние роутера обновляется чуть позже самой записи, сравнивать адреса нельзя.
let urlWrites = 0;
export const outcomeUrlWrites = (): number => urlWrites;

export type OutcomeUrlControls = {
  state: OutcomeUrlState;
  /**
   * Изменить часть состояния; `push` добавляет запись в историю (по умолчанию замена). `navState`
   * кладётся в запись истории (телефон помечает так открытые листы: `lib/phoneNav.ts`); замена
   * сохраняет состояние текущей записи, чтобы правка адреса внутри листа его не закрывала.
   */
  update: (
    patch: Partial<OutcomeUrlState>,
    push?: boolean,
    navState?: unknown,
  ) => void;
};

/** Состояние экрана «Результат» из адреса и запись обратно. */
export const useOutcomeUrlState = (): OutcomeUrlControls => {
  const [params, setParams] = useSearchParams();
  const location = useLocation();
  const override = useContext(OutcomeSearchContext);
  const key = override ? override.search : params.toString();
  const state = useMemo(
    () => parseOutcomeSearch(new URLSearchParams(key)),
    [key],
  );
  const set = override?.set;
  const here: unknown = location.state;
  const update = useCallback(
    (patch: Partial<OutcomeUrlState>, push = false, navState?: unknown) => {
      urlWrites += 1;
      if (set) {
        set(writeOutcomeSearch(new URLSearchParams(key), patch));
        return;
      }
      setParams((prev) => writeOutcomeSearch(prev, patch), {
        replace: !push,
        state: push ? navState : here,
      });
    },
    [here, key, set, setParams],
  );
  return { state, update };
};
