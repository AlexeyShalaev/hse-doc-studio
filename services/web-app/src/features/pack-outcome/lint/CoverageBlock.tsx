import { useState } from "react";
import { CircleCheck, CircleDashed, CircleDot, Plus } from "lucide-react";
import { useTranslation } from "react-i18next";
import type { OutcomeCoverage, RuleCoverage } from "@entities/pack-studio";
import { coveragePercent, isUncoveredRule, missingOutcomes } from "../lib/lint";
import { useScenarioUi } from "../ui/scenarios/context";
import { useLintActions } from "./context";
import { WitnessLine } from "./WitnessLine";

/** Сколько правил без полного покрытия показывать сразу: остальные по кнопке. */
const RULES_SHOWN = 8;
/** Не больше строк, чем отдаёт сервер (до десяти). */
const MAX_ROWS = 10;

type RuleItemProps = { rule: RuleCoverage };

/** Правило, которое сценарии проверили не до конца: что видели, чего не хватает, свидетель. */
const RuleItem = ({ rule }: RuleItemProps) => {
  const { t } = useTranslation("packOutcome");
  const { openRule } = useLintActions();
  const none = isUncoveredRule(rule);
  const kind = t(`rules.kinds.${rule.kind}`, { defaultValue: rule.kind });
  const ruleName =
    rule.rule.origin === "builtin"
      ? `${kind}: ${t(`rules.builtin.${rule.rule.builtin ?? ""}`, {
          defaultValue: t("rules.builtin.other"),
        })}`
      : kind;
  const Icon = none ? CircleDashed : CircleDot;
  const outcomes = (list: readonly string[]): string =>
    list.map((outcome) => t(`lint.coverage.outcome.${outcome}`)).join(", ");
  const where = [rule.rule.file, rule.rule.pointer]
    .filter((part) => part !== null)
    .join(" ");
  return (
    <li
      className="ln-rule-item"
      data-state={none ? "none" : "half"}
      data-testid="outcome-lint-coverage-rule"
    >
      <div className="ln-finding-head">
        <span className="ln-sev" data-coverage={none ? "none" : "half"}>
          <Icon size="0.875rem" aria-hidden="true" />
          <span>
            {t(none ? "lint.coverage.stateNone" : "lint.coverage.stateHalf")}
          </span>
        </span>
        <span className="ln-rule-name">{ruleName}</span>
      </div>
      {where !== "" && <p className="po-mono ln-where">{where}</p>}
      <p className="po-note">
        {rule.seen.length > 0
          ? t("lint.coverage.seen", { outcomes: outcomes(rule.seen) })
          : t("lint.coverage.seenNone")}{" "}
        {missingOutcomes(rule).length > 0 &&
          t("lint.coverage.missing", {
            outcomes: outcomes(missingOutcomes(rule)),
          })}{" "}
        {t("lint.coverage.byScenarios", { count: rule.scenarios.length })}
      </p>
      {rule.witness ? <WitnessLine witness={rule.witness} /> : null}
      {rule.rule.origin === "manifest" && rule.rule.file !== null ? (
        <div className="ln-actions">
          <button
            type="button"
            className="btn sm"
            data-testid="outcome-lint-open-coverage-rule"
            onClick={() => {
              openRule(rule.rule);
            }}
          >
            {t("lint.finding.openRule")}
          </button>
        </div>
      ) : null}
    </li>
  );
};

type CoverageBlockProps = { coverage: OutcomeCoverage };

/**
 * Покрытие правил сценариями: процент, сколько правил покрыто полностью, наполовину и совсем не
 * покрыто, правила без полного покрытия со свидетелем и подсказки «Добавить сценарии». Все числа и
 * строки приходят в ответе сервера (`coverage`), здесь они только разложены.
 */
export const CoverageBlock = ({ coverage }: CoverageBlockProps) => {
  const { t } = useTranslation("packOutcome");
  const { addScenario, canAddScenario, showCombination, labeler } =
    useLintActions();
  const ui = useScenarioUi();
  const [all, setAll] = useState(false);
  const [open, setOpen] = useState(false);
  const percent = coveragePercent(coverage);
  const rules = [...coverage.rules].sort(
    (a, b) => Number(isUncoveredRule(b)) - Number(isUncoveredRule(a)),
  );
  const shown = all ? rules : rules.slice(0, RULES_SHOWN);
  const rows = coverage.uncovered_rows ?? [];
  const reason =
    ui?.readOnlyReason === "student"
      ? t("scenarios.readOnlyStudent")
      : ui?.readOnlyReason === "state"
        ? t("scenarios.readOnlyState")
        : undefined;
  return (
    <section
      className="ln-coverage"
      aria-labelledby="ln-coverage-title"
      data-testid="outcome-lint-coverage"
    >
      <h3 className="ln-block-title" id="ln-coverage-title">
        {t("lint.coverage.title")}
      </h3>
      <div className="ln-percent">
        <span className="ln-percent-num" data-testid="outcome-lint-percent">
          {t("lint.coverage.percent", { percent })}
        </span>
        <progress
          className="ln-progress"
          max={100}
          value={percent}
          aria-label={t("lint.coverage.percentLabel", { percent })}
        />
      </div>
      {coverage.approximate === true && (
        <p
          className="po-note ln-approx"
          role="status"
          data-testid="outcome-lint-approximate"
        >
          {t("lint.coverage.approximate")}
        </p>
      )}
      <ul className="ln-tally" aria-label={t("lint.coverage.rulesLabel")}>
        <li data-state="full">
          <CircleCheck size="0.875rem" aria-hidden="true" />
          {t("lint.coverage.covered", { count: coverage.rules_covered })}
        </li>
        <li data-state="half">
          <CircleDot size="0.875rem" aria-hidden="true" />
          {t("lint.coverage.half", { count: coverage.rules_half })}
        </li>
        <li data-state="none">
          <CircleDashed size="0.875rem" aria-hidden="true" />
          {t("lint.coverage.uncovered", { count: coverage.rules_uncovered })}
        </li>
      </ul>
      <p className="po-note">
        {t("lint.coverage.scenarios", { count: coverage.scenarios })}
        {coverage.rows_total !== undefined &&
          coverage.rows_touched !== undefined &&
          ` ${t("lint.coverage.rows", {
            touched: coverage.rows_touched,
            total: coverage.rows_total,
          })}`}
      </p>

      {rows.length > 0 || coverage.scenarios === 0 ? (
        <div className="ln-suggest" data-testid="outcome-lint-suggest">
          <button
            type="button"
            className="btn sm"
            aria-expanded={open}
            disabled={!canAddScenario}
            title={reason}
            data-testid="outcome-lint-add-scenarios"
            onClick={() => {
              if (rows.length === 0) addScenario(null);
              else setOpen(!open);
            }}
          >
            <Plus size="0.8125rem" aria-hidden="true" />
            {rows.length > 0
              ? t("lint.coverage.addMany", { count: rows.length })
              : t("lint.coverage.addOne")}
          </button>
          {open && rows.length > 0 && (
            <ul
              className="ln-rows"
              aria-label={t("lint.coverage.rowsLabel")}
              data-testid="outcome-lint-uncovered-rows"
            >
              {rows.slice(0, MAX_ROWS).map((row, index) => (
                <li key={index} className="ln-row">
                  <p className="ln-witness-text">
                    {Object.entries(row.inputs)
                      .map(
                        ([input, value]) =>
                          `${labeler.input(input)}: ${labeler.value(input, value)}`,
                      )
                      .join("; ")}
                  </p>
                  <p className="po-note">
                    {t("lint.coverage.gain", { count: row.gain })}
                  </p>
                  <div className="ln-actions">
                    <button
                      type="button"
                      className="btn sm"
                      data-testid="outcome-lint-add-row"
                      onClick={() => {
                        addScenario(row.inputs);
                      }}
                    >
                      <Plus size="0.8125rem" aria-hidden="true" />
                      {t("lint.coverage.addRow")}
                    </button>
                    <button
                      type="button"
                      className="btn sm"
                      onClick={() => {
                        showCombination(row.inputs);
                      }}
                    >
                      {t("lint.finding.showCombo")}
                    </button>
                  </div>
                </li>
              ))}
            </ul>
          )}
        </div>
      ) : null}

      {rules.length > 0 && (
        <div className="ln-rules-block">
          <h4 className="ln-subtitle">{t("lint.coverage.rulesTitle")}</h4>
          <ul
            className="ln-list"
            aria-label={t("lint.coverage.rulesTitle")}
            data-testid="outcome-lint-coverage-rules"
          >
            {shown.map((rule, index) => (
              <RuleItem
                key={`${rule.rule.file ?? ""}${rule.rule.pointer ?? ""}${rule.rule.builtin ?? ""}${String(index)}`}
                rule={rule}
              />
            ))}
          </ul>
          {!all && rules.length > RULES_SHOWN && (
            <button
              type="button"
              className="btn sm"
              data-testid="outcome-lint-rules-all"
              onClick={() => {
                setAll(true);
              }}
            >
              {t("lint.coverage.showAll", { count: rules.length })}
            </button>
          )}
        </div>
      )}
      {(coverage.rules_omitted ?? 0) > 0 && (
        <p className="po-note" data-testid="outcome-lint-omitted">
          {t("lint.coverage.omitted", { count: coverage.rules_omitted })}
        </p>
      )}
    </section>
  );
};
