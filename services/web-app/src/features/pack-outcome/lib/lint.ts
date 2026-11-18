import type {
  OutcomeCoverage,
  OutcomeElementRef,
  OutcomeFinding,
  RuleCoverage,
} from "@entities/pack-studio";
import type { OutcomeSelection } from "./urlState";

// Находки линтера результата, покрытие и подсказки: всё посчитал сервер (R1), здесь только
// раскладка по группам, поиск и подписи. Условий пака клиент не знает.

export type Severity = OutcomeFinding["severity"];
export const SEVERITIES: readonly Severity[] = ["error", "warning", "info"];

/** Находка с устойчивым номером из ответа: ключ строки и «Открыть» не зависят от фильтров. */
export type IndexedFinding = { id: string; finding: OutcomeFinding };

export type LintFilter = {
  /** `null`: все уровни. */
  severity: Severity | null;
  /** `null`: все правила. */
  rule: string | null;
  query: string;
  /** Только находки выбранного на экране элемента. */
  selectedOnly: boolean;
};

export const NO_FILTER: LintFilter = {
  severity: null,
  rule: null,
  query: "",
  selectedOnly: false,
};

export type RuleGroup = { rule: string; items: IndexedFinding[] };
export type SeverityGroup = {
  severity: Severity;
  count: number;
  rules: RuleGroup[];
};

export const indexFindings = (
  findings: readonly OutcomeFinding[],
): IndexedFinding[] =>
  findings.map((finding, index) => ({
    id: `${finding.rule_id}-${String(index)}`,
    finding,
  }));

export const touches = (
  finding: OutcomeFinding,
  element: OutcomeSelection | OutcomeElementRef | null,
): boolean =>
  element !== null &&
  finding.elements.some(
    (item) => item.section === element.section && item.id === element.id,
  );

const matches = (finding: OutcomeFinding, query: string): boolean => {
  const needle = query.trim().toLocaleLowerCase();
  if (needle === "") return true;
  return [
    finding.rule_id,
    finding.message,
    finding.hint ?? "",
    finding.file ?? "",
    finding.pointer ?? "",
    ...finding.elements.map((item) => `${item.section}:${item.id}`),
  ].some((text) => text.toLocaleLowerCase().includes(needle));
};

/** Находки по фильтру, сгруппированные по уровню (ошибки, предупреждения, информация) и правилу. */
export const groupFindings = (
  findings: readonly OutcomeFinding[],
  filter: LintFilter,
  selected: OutcomeSelection | null,
): SeverityGroup[] => {
  const kept = indexFindings(findings).filter(
    ({ finding }) =>
      (filter.severity === null || finding.severity === filter.severity) &&
      (filter.rule === null || finding.rule_id === filter.rule) &&
      (!filter.selectedOnly || touches(finding, selected)) &&
      matches(finding, filter.query),
  );
  return SEVERITIES.flatMap((severity) => {
    const items = kept.filter((item) => item.finding.severity === severity);
    if (items.length === 0) return [];
    const rules = new Map<string, IndexedFinding[]>();
    for (const item of items) {
      const list = rules.get(item.finding.rule_id) ?? [];
      list.push(item);
      rules.set(item.finding.rule_id, list);
    }
    return [
      {
        severity,
        count: items.length,
        rules: [...rules.entries()].map(([rule, list]) => ({
          rule,
          items: list,
        })),
      },
    ];
  });
};

/** Правила, по которым есть находки, с числом: для списка фильтра. */
export const rulesOf = (
  findings: readonly OutcomeFinding[],
): { rule: string; count: number }[] => {
  const counts = new Map<string, number>();
  for (const finding of findings) {
    counts.set(finding.rule_id, (counts.get(finding.rule_id) ?? 0) + 1);
  }
  return [...counts.entries()]
    .map(([rule, count]) => ({ rule, count }))
    .sort((a, b) => (a.rule < b.rule ? -1 : a.rule > b.rule ? 1 : 0));
};

export type LintCounts = { errors: number; warnings: number; infos: number };

export const countsOf = (lint: {
  errors: number;
  warnings: number;
  infos?: number | undefined;
}): LintCounts => ({
  errors: lint.errors,
  warnings: lint.warnings,
  infos: lint.infos ?? 0,
});

/** Правило не покрыто совсем, если сценарии не видели ни одного его исхода. */
export const isUncoveredRule = (rule: RuleCoverage): boolean =>
  rule.seen.length === 0;

/**
 * Процент покрытия: сервер присылает `percent`; у старого ответа без него берётся доля правил,
 * покрытых полностью (счёт по готовым числам ответа, не по условиям).
 */
export const coveragePercent = (coverage: OutcomeCoverage): number => {
  if (coverage.percent !== undefined) return coverage.percent;
  return coverage.rules_total === 0
    ? 100
    : Math.round((coverage.rules_covered / coverage.rules_total) * 1000) / 10;
};

/** Какие исходы правила сценарии не видели: из достижимых без увиденных. */
export const missingOutcomes = (
  rule: RuleCoverage,
): ("held" | "not_held")[] => {
  const possible = rule.possible ?? ["held", "not_held"];
  return possible.filter((outcome) => !rule.seen.includes(outcome));
};

/** Не более трёх свидетелей, чтобы ответ с неожиданными данными не раздул карточку. */
export const MAX_WITNESSES = 3;
