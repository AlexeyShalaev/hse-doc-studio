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
