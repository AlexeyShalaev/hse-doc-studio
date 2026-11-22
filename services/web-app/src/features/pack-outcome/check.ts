// Публичное для области «Проверка» нового интерфейса (features/pack-space/check,
// docs/design/pack-studio-ux.md, срез S10): модели и чистые функции прежних режимов («Проверка пака»,
// «Матрица», «Атлас», «Сравнить»), подписи вводных и сам режим «Сравнить». Новая область читает
// те же ответы сервера и считает их так же; здесь ничего не меняется, только открывается наружу.
import "./modes/modes.css";

export { CompareMode } from "./modes/CompareMode";
export { ChangeList } from "./modes/ChangeList";
export { ChangeEnvContext } from "./modes/changeEnv";
export { ChangeWordsContext } from "./modes/changeWords";
export type { ChangeWords } from "./modes/changeWords";
export type { ChangeEnv } from "./modes/changeEnv";
export { useLabeler } from "./ui/inputs/useLabeler";
export type { Labeler } from "./ui/inputs/useLabeler";
export { personaLabel } from "./lib/personas";
export { ruleLocation } from "./lib/rules";
export { formatSide, parseSide } from "./lib/compareSide";
export type { CompareSide } from "./lib/compareSide";
export {
  MAX_WITNESSES,
  SEVERITIES,
  countsOf,
  coveragePercent,
  indexFindings,
  isUncoveredRule,
  missingOutcomes,
  rulesOf,
} from "./lib/lint";
export type { IndexedFinding, LintCounts, Severity } from "./lib/lint";
export { cellOf, countCells, fingerprintGroups, tallyRows } from "./lib/matrix";
export {
  EMPTY_FILTER,
  applyRowInputs,
  filterRows,
  keyOfInputs,
  miniOf,
  rowValues,
  withPin,
} from "./lib/atlas";
export type { AtlasFilter, AtlasRowView, OutcomeMini } from "./lib/atlas";
export {
  ASSERTION_KINDS,
  SCENARIO_LANGS,
  assertionKey,
  badgeOf,
  classifyFailure,
  formOf,
  mergedInputs,
  nameProblem,
  requestOf,
  resultsById,
  retryable,
  scenarioName,
  suggestAssertions,
  tallyOf,
} from "./lib/scenarios";
export type {
  AssertionKind,
  RunTally,
  ScenarioBadge,
  ScenarioFailure,
  ScenarioForm,
} from "./lib/scenarios";
export { StudentView } from "./ui/student/StudentView";
