import type {
  OutcomeElementRef,
  OutcomeInput,
  PackOutcome,
  PackOutcomeInputs,
  PackScenarioList,
} from "@entities/pack-studio";

// Чистые помощники панели «Вводные»: что считать исходным значением, какие вводные не влияют,
// какие элементы результата с ними связаны. Условий пака здесь нет: всё берётся из ответов
// сервера (`inputs`, трасса результата), клиент только раскладывает его по местам.

/** Вводные с готовыми подписями в словаре интерфейса (раздел 2.1 дизайна). */
export const STANDARD_INPUTS: readonly string[] = [
  "lang",
  "kind",
  "staffing",
  "supervisor",
  "co_supervisor",
  "academic_supervisor",
];

const TOKEN = /^[a-z][a-z0-9_]*$/;

/** Значение годится в ключ словаря (токен без точек и пробелов). */
export const isToken = (value: string): boolean => TOKEN.test(value);

/** Вводная ничего не меняет в разделах результата: `affects` пуст (атлас: no_effect или cosmetic). */
export const isInert = (input: OutcomeInput): boolean =>
  input.affects.length === 0;

/** Пары `раздел:id` в одну строку для множества. */
export const elementKey = (element: OutcomeElementRef): string =>
  `${element.section}:${element.id}`;

export type InputsBaseline = {
  /** Вводные выбранного сценария (частичные); пусто, если сценария нет или он не разобран. */
  scenario: Record<string, string>;
  /** Набор данных, с которым считается результат без явного выбора. */
  example: string;
  scenarioName: Record<string, string> | null;
};

/**
 * Исходные значения, поверх которых лежат изменения из адреса. Порядок из дизайна (раздел 2.1):
 * умолчания версии, набор данных, вводные сценария. Здесь два последних слоя; умолчания версии
 * лежат в самих вводных.
 */
export const baselineOf = (
  data: PackOutcomeInputs,
  scenarios: PackScenarioList | undefined,
  scenarioId: string | null,
): InputsBaseline => {
  const entry =
    scenarioId === null
      ? undefined
      : scenarios?.scenarios.find((item) => item.id === scenarioId);
  const scenario = entry?.scenario ?? null;
  return {
    scenario: scenario?.inputs ?? {},
    example: scenario?.example ?? data.default_example,
    scenarioName: scenario?.name ?? null,
  };
};

/** Значение вводной без изменений из адреса: сценарий, затем умолчание версии. */
export const baseValue = (
  input: OutcomeInput,
  baseline: InputsBaseline,
  exampleDefaults: Record<string, string>,
): string =>
  baseline.scenario[input.id] ?? exampleDefaults[input.id] ?? input.default;

/** Значения вводных, которые набор данных задаёт сам (`lang`, `kind`, `staffing` из примера). */
export const exampleDefaultsOf = (
  data: PackOutcomeInputs,
  exampleId: string,
): Record<string, string> =>
  data.examples.find((item) => item.id === exampleId)?.defaults ?? {};

/**
 * Изменения поверх исходных значений: значение, равное исходному, в адрес не пишется, а прежнее
 * изменение при возврате к исходному убирается.
 */
export const withValue = (
  overrides: Record<string, string>,
  id: string,
  value: string,
  base: string,
): Record<string, string> => {
  const rest = Object.entries(overrides).filter(([key]) => key !== id);
  if (value !== base) rest.push([id, value]);
  return Object.fromEntries(rest);
};

export const sameInputs = (
  a: Record<string, string>,
  b: Record<string, string>,
): boolean => {
  const keys = Object.keys(a);
  return (
    keys.length === Object.keys(b).length &&
    keys.every((key) => a[key] === b[key])
  );
};

/**
 * Элементы результата, о которых есть решения, читающие вводную: связи отдаёт трасса ответа
 * (`terms[].subject` совпадает с id вводной, `subjects` перечисляет элементы). Если трасса вводную
 * не читает, связей нет и подсвечивать нечего: догадок здесь не делается.
 */
export const linkedElements = (
  outcome: PackOutcome | undefined,
  inputId: string,
): OutcomeElementRef[] => {
  if (!outcome) return [];
  const seen = new Set<string>();
  const out: OutcomeElementRef[] = [];
  for (const decision of outcome.trace) {
    if (!decision.terms.some((term) => term.subject === inputId)) continue;
    for (const element of decision.subjects) {
      const key = elementKey(element);
      if (seen.has(key)) continue;
      seen.add(key);
      out.push(element);
    }
  }
  return out;
};
