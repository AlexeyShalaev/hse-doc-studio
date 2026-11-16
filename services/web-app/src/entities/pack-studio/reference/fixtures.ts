import { z } from "zod";
import {
  OutcomeBranchSchema,
  OutcomeCheckRuleSchema,
  PackOutcomeInputsSchema,
  PackOutcomeSchema,
  PackScenarioListSchema,
  PackScenarioRunSchema,
  type OutcomeBranch,
  type OutcomeCheckRule,
  type PackOutcome,
  type PackOutcomeInputs,
  type PackScenarioList,
  type PackScenarioRun,
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
const runFiles = import.meta.glob<unknown>(
  "../../../../../../contracts/pack-studio/fixtures/PackScenarioRun/*.json",
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
/** Прогон сценариев курсового после правки правила: два совпали, один изменился. */
export const COURSEWORK_RUN: PackScenarioRun = PackScenarioRunSchema.parse(
  load(runFiles, "PackScenarioRun", "coursework_after_edit"),
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
// Эталон ВКР отдаёт `checks` и `branches` пустыми (`include` не просили). Чтобы экран «Результат» в
// режиме эталонов и в галерее показывал эти разделы на ВКР, здесь заведены свои значения: правила
// и ветки собраны вручную по вводным и документам ВКР, цифры иллюстративные. Контракт и сервер
// их не используют, это данные только для разработки экрана.

const rule = (
  id: string,
  ru: string,
  en: string,
  category: string,
  severity: "info" | "warn" | "err",
  engine: string,
  appliesTo: string[],
  off: OutcomeCheckRule["off_reason"] = null,
) => ({
  id,
  title: { ru, en },
  category,
  severity,
  engine,
  enabled: off === null,
  off_reason: off,
  applies_to: appliesTo,
  why: [],
});

/** Правила проверок ВКР: по слоям гост-файлов, с выключенными и без документа. */
export const VKR_CHECKS: OutcomeCheckRule[] = z
  .array(OutcomeCheckRuleSchema)
  .parse([
    rule(
      "gost-7.32-2017/page-margins",
      "Поля страницы",
      "Page margins",
      "formatting",
      "warn",
      "structural",
      ["thesis"],
    ),
    rule(
      "gost-7.32-2017/line-spacing",
      "Межстрочный интервал 1.5",
      "Line spacing 1.5",
      "formatting",
      "warn",
      "structural",
      ["thesis"],
    ),
    rule(
      "gost-7.32-2017/section-introduction",
      "Есть введение",
      "Introduction present",
      "structure",
      "err",
      "regex",
      ["thesis"],
    ),
    rule(
      "gost-7.32-2017/bibliography-section",
      "Есть список источников",
      "Bibliography present",
      "structure",
      "err",
      "regex",
      ["thesis"],
    ),
    rule(
      "gost-7.32-2017/dangling-cite",
      "Ссылка на отсутствующий источник",
      "Dangling citation",
      "bibliography",
      "warn",
      "log_parse",
      ["thesis"],
    ),
    rule(
      "gost-7.32-2017/list-style",
      "Единый стиль списков",
      "Consistent list style",
      "formatting",
      "info",
      "python",
      ["thesis"],
    ),
    rule(
      "typography-ru/quotes",
      "Кавычки-ёлочки",
      "Guillemet quotes",
      "formatting",
      "info",
      "typography",
      ["thesis"],
    ),
    rule(
      "hse-cs-se-vkr/section-sources",
      "Источники в техническом задании",
      "Sources in the specification",
      "structure",
      "warn",
      "regex",
      ["technical_specification"],
    ),
    rule(
      "hse-cs-se-vkr/spec-placeholders",
      "Незаполненные заготовки",
      "Placeholders left",
      "content",
      "warn",
      "python",
      ["technical_specification", "test_program_and_methodology"],
    ),
    rule(
      "hse-cs-se-vkr/manual-contacts",
      "Контакты в руководстве оператора",
      "Contacts in the operator manual",
      "content",
      "info",
      "python",
      ["operator_manual"],
      "no_active_document",
    ),
    rule(
      "hse-cs-se-vkr/annotation-length",
      "Длина аннотации",
      "Annotation length",
      "content",
      "info",
      "python",
      ["annotation"],
      "no_active_document",
    ),
    rule(
      "typography-ru/ellipsis",
      "Многоточие",
      "Ellipsis",
      "formatting",
      "info",
      "typography",
      ["thesis"],
      "category_disabled",
    ),
    rule(
      "gost-7.32-2017/figure-numbering",
      "Нумерация рисунков",
      "Figure numbering",
      "references",
      "info",
      "structural",
      ["thesis"],
      "disabled",
    ),
  ]);

const print = (value: string) => ({ value, label: null, fingerprint: value });

/** Ветки ВКР: что станет при другом значении вводной (счётчики по разделам). */
export const VKR_BRANCHES: OutcomeBranch[] = z
  .array(OutcomeBranchSchema)
  .parse([
    {
      input: "kind",
      label: null,
      chosen: "project",
      affects: ["documents", "meta", "points", "route"],
      alternatives: [
        { ...print("project"), fingerprint: "0a1b2c3d4e5f6071", delta: [] },
        {
          ...print("research"),
          fingerprint: "1b2c3d4e5f607182",
          delta: [
            { section: "documents", added: 3, changed: 0, removed: 7 },
            { section: "meta", added: 0, changed: 2, removed: 1 },
            { section: "points", added: 0, changed: 2, removed: 0 },
          ],
        },
      ],
    },
    {
      input: "staffing",
      label: null,
      chosen: "solo",
      affects: ["documents", "participants", "points", "route"],
      alternatives: [
        { ...print("solo"), fingerprint: "2c3d4e5f60718293", delta: [] },
        {
          ...print("team2"),
          fingerprint: "3d4e5f6071829304",
          delta: [
            { section: "documents", added: 0, changed: 11, removed: 0 },
            { section: "participants", added: 1, changed: 0, removed: 0 },
            { section: "route", added: 4, changed: 2, removed: 0 },
          ],
        },
        {
          ...print("team3"),
          fingerprint: "4e5f607182930415",
          delta: [
            { section: "documents", added: 0, changed: 11, removed: 0 },
            { section: "participants", added: 2, changed: 0, removed: 0 },
            { section: "route", added: 8, changed: 2, removed: 0 },
          ],
        },
      ],
    },
    {
      input: "meta.nda",
      label: { ru: "NDA", en: "NDA" },
      chosen: "yes",
      affects: ["documents", "points"],
      alternatives: [
        {
          ...print("no"),
          fingerprint: "5f60718293041526",
          delta: [{ section: "documents", added: 1, changed: 0, removed: 0 }],
        },
        { ...print("yes"), fingerprint: "607182930415263e", delta: [] },
      ],
    },
    {
      input: "academic_supervisor",
      label: null,
      chosen: "yes",
      affects: ["participants"],
      alternatives: [
        { ...print("yes"), fingerprint: "7182930415263e4f", delta: [] },
        {
          ...print("no"),
          fingerprint: "82930415263e4f50",
          delta: [
            { section: "participants", added: 0, changed: 0, removed: 1 },
          ],
        },
      ],
    },
  ]);
