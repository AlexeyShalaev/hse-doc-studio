import {
  PackOutcomeInputsSchema,
  PackOutcomeSchema,
  PackScenarioListSchema,
  type PackOutcome,
  type PackOutcomeInputs,
  type PackScenarioList,
} from "../api/outcome";

// Эталоны контракта вычислителя (contracts/pack-studio/fixtures), собранные в браузере. Модуль
// только для разработки и тестов: в рабочую сборку не попадает (его подключают динамическим
// import() под import.meta.env.DEV). Те же файлы разбирают тесты контракта и бэкенда, так что
// расхождение схемы и эталона видно сразу: здесь каждый файл проходит строгую схему.

const load = (
  files: Record<string, unknown>,
  dir: string,
  name: string,
): unknown => {
  const found = Object.entries(files).find(([path]) =>
    path.endsWith(`/${dir}/${name}.json`),
  );
  if (!found) throw new Error(`reference fixture ${dir}/${name} is missing`);
  return found[1];
};

const outcomeFiles = import.meta.glob<unknown>(
  "../../../../../../contracts/pack-studio/fixtures/PackOutcome/*.json",
  { eager: true, import: "default" },
);
const inputsFiles = import.meta.glob<unknown>(
  "../../../../../../contracts/pack-studio/fixtures/PackOutcomeInputs/*.json",
  { eager: true, import: "default" },
);
const scenarioFiles = import.meta.glob<unknown>(
  "../../../../../../contracts/pack-studio/fixtures/PackScenarioList/*.json",
  { eager: true, import: "default" },
);

/** ВКР бакалавриата с NDA и руководствами «только программиста» (18 документов, 6 точек). */
export const VKR_OUTCOME: PackOutcome = PackOutcomeSchema.parse(
  load(outcomeFiles, "PackOutcome", "vkr_nda_programmer_only"),
);
/** Курсовой проект магистратуры: научрук из компании, консультант (4 документа, 4 точки). */
export const COURSEWORK_OUTCOME: PackOutcome = PackOutcomeSchema.parse(
  load(outcomeFiles, "PackOutcome", "coursework_company_cosupervisor"),
);
export const VKR_INPUTS: PackOutcomeInputs = PackOutcomeInputsSchema.parse(
  load(inputsFiles, "PackOutcomeInputs", "vkr"),
);
export const COURSEWORK_SCENARIOS: PackScenarioList =
  PackScenarioListSchema.parse(
    load(scenarioFiles, "PackScenarioList", "coursework"),
  );

const STANDARD_INPUT_IDS = [
  "lang",
  "kind",
  "staffing",
  "supervisor",
  "co_supervisor",
  "academic_supervisor",
];

/**
 * Вводные курсового проекта. Эталона `PackOutcomeInputs` для него нет, поэтому словарь собран из
 * того, что есть: стандартные вводные берутся у ВКР, поля select и вариант презентации из
 * результата курсового (`meta[].options`, значения `inputs`), а `affects` и `rules` считаются по
 * трассе того же результата (какие разделы и сколько правил читают вводную).
 */
const buildCourseworkInputs = (): PackOutcomeInputs => {
  const outcome = COURSEWORK_OUTCOME;
  const read = (id: string) =>
    outcome.trace.filter((decision) =>
      decision.terms.some((term) => term.subject === id),
    );
  const standard = VKR_INPUTS.inputs.filter((input) =>
    STANDARD_INPUT_IDS.includes(input.id),
  );
  const selects = outcome.meta
    .filter((field) => field.type === "select" && field.options.length > 0)
    .map((field) => ({
      id: `meta.${field.id}`,
      group: "meta" as const,
      type: "select" as const,
      label: field.label,
      values: field.options.map((option) => ({ value: option, label: null })),
      default: field.options[0] ?? "",
    }));
  const variant = VKR_INPUTS.inputs.filter(
    (input) => input.id === "variant.presentation",
  );
  const inputs = [...standard, ...selects, ...variant].map((input) => {
    const decisions = read(input.id);
    const sections = new Set(
      decisions.flatMap((decision) =>
        decision.subjects.map((element) => element.section),
      ),
    );
    return {
      ...input,
      affects: [...sections],
      rules: decisions.length,
    };
  });
  return {
    ...VKR_INPUTS,
    template: outcome.template,
    version: outcome.version,
    inputs,
    defaults: Object.fromEntries(
      inputs.map((input) => [input.id, input.default]),
    ),
  };
};

export const COURSEWORK_INPUTS: PackOutcomeInputs =
  PackOutcomeInputsSchema.parse(buildCourseworkInputs());
