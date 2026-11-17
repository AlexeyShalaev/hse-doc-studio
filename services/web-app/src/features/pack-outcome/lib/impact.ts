import type { TFunction } from "i18next";
import type {
  OutcomeChange,
  PackOutcomeImpact,
  PackVersionRef,
} from "@entities/pack-studio";
import { pickLocalized } from "@shared/lib/i18n/pickLocalized";

// «До и после» в «Предложить изменения» (срез F10). Различия и статусы считает сервер (`impact`),
// здесь только вердикт для подтверждения и компактный текст для тела PR или MR.

export type ImpactVerdict = {
  total: number;
  changed: number;
  errors: number;
  /** Изменившихся и упавших сценариев нет, а находки и атлас не в счёт. */
  needsAck: boolean;
  /** Что-то изменилось: сценарий, строка атласа или раздел, или есть новые находки. */
  any: boolean;
};

export const impactVerdict = (impact: PackOutcomeImpact): ImpactVerdict => {
  const { summary } = impact;
  const changed = summary.scenarios_changed;
  const errors = summary.scenarios_error;
  const atlasRows = summary.atlas?.rows_changed ?? 0;
  const sections = summary.sections.some(
    (s) => s.added + s.changed + s.removed > 0,
  );
  return {
    total: summary.scenarios_total,
    changed,
    errors,
    needsAck: changed + errors > 0,
    any:
      changed + errors > 0 ||
      atlasRows > 0 ||
      sections ||
      impact.new_findings.length > 0,
  };
};

/** Счётчики `+`, `~`, `-` по списку изменений. */
export const countChanges = (
  changes: readonly OutcomeChange[],
): { added: number; changed: number; removed: number } => {
  let added = 0;
  let changed = 0;
  let removed = 0;
  for (const change of changes) {
    if (change.symbol === "+") added += 1;
    else if (change.symbol === "~") changed += 1;
    else removed += 1;
  }
  return { added, changed, removed };
};

/** Всего по разделам сводки. */
export const totalDelta = (
  sections: PackOutcomeImpact["summary"]["sections"],
): { added: number; changed: number; removed: number } =>
  sections.reduce(
    (sum, s) => ({
      added: sum.added + s.added,
      changed: sum.changed + s.changed,
      removed: sum.removed + s.removed,
    }),
    { added: 0, changed: 0, removed: 0 },
  );

export const versionKey = (v: PackVersionRef): string =>
  `${v.pack}/${v.template}/${v.version}`;

export type ImpactEntry = { ref: PackVersionRef; impact: PackOutcomeImpact };

const MAX_SCENARIOS = 8;
const MAX_CHANGES = 3;
const MAX_TEXT = 3000;

/**
 * Сводка для тела PR или MR: на языке интерфейса, коротко. Заголовок «изменится результат в N из M
 * сценариев», строка атласа и до восьми сценариев с тремя изменениями каждый. Подписи и названия
 * приходят от сервера (из пака), персональных данных в них нет. Пусто, если результат не менялся.
 */
export const impactSummaryText = (
  t: TFunction<"packOutcome">,
  lang: string,
  entries: readonly ImpactEntry[],
): string => {
  const lines: string[] = [];
  for (const { ref, impact } of entries) {
    const verdict = impactVerdict(impact);
    if (!verdict.any) continue;
    const { summary } = impact;
    if (entries.length > 1) {
      lines.push(`**${ref.pack} / ${ref.template} ${ref.version}**`);
    }
    lines.push(
      verdict.changed + verdict.errors > 0
        ? t("impact.pr.head", {
            changed: verdict.changed + verdict.errors,
            total: verdict.total,
            count: verdict.total,
          })
        : t("impact.pr.headNone", { total: verdict.total }),
    );
    if (summary.atlas && summary.atlas.rows_changed > 0) {
      lines.push(
        t("impact.pr.atlas", {
          changed: summary.atlas.rows_changed,
          total: summary.atlas.rows_total,
          before: summary.atlas.outcomes_before,
          after: summary.atlas.outcomes_after,
        }),
      );
    }
    const shown = impact.scenarios.filter((s) => s.status !== "unchanged");
    for (const scenario of shown.slice(0, MAX_SCENARIOS)) {
      const name = pickLocalized(scenario.name, lang, scenario.scenario);
      if (scenario.status === "error") {
        lines.push(`- ${name}: ${t("impact.pr.error")}`);
        continue;
      }
      const n = countChanges(scenario.changes);
      lines.push(
        `- ${name}: +${String(n.added)} ~${String(n.changed)} -${String(n.removed)}`,
      );
      for (const change of scenario.changes.slice(0, MAX_CHANGES)) {
        lines.push(`  - \`${change.symbol}\` ${change.label}`);
      }
    }
    if (shown.length > MAX_SCENARIOS) {
      lines.push(t("impact.pr.more", { count: shown.length - MAX_SCENARIOS }));
    }
    if (impact.new_findings.length > 0) {
      lines.push(
        t("impact.pr.findings", { count: impact.new_findings.length }),
      );
    }
  }
  if (lines.length === 0) return "";
  const text = [`### ${t("impact.title")}`, "", ...lines].join("\n");
  return text.length > MAX_TEXT ? `${text.slice(0, MAX_TEXT - 1)}…` : text;
};
