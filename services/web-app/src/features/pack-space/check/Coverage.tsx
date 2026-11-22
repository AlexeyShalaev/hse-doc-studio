import { useState } from "react";
import { CircleCheck, CircleDashed, CircleDot, Plus } from "lucide-react";
import { useTranslation } from "react-i18next";
import type { OutcomeCoverage, RuleCoverage } from "@entities/pack-studio";
import {
  coveragePercent,
  isUncoveredRule,
  missingOutcomes,
} from "@entities/pack-studio/outcome/lint";
import { SituationText, Witness } from "./Findings";
import type { CheckEnv } from "./useCheckEnv";

/** Сколько правил без полной проверки показывать сразу: остальные по кнопке. */
const RULES_SHOWN = 8;
/** Не больше строк, чем отдаёт сервер (до десяти). */
const MAX_ROWS = 10;

/** Правило, которое готовые случаи проверили не до конца: что видели, чего не хватает, пример. */
const RuleItem = ({ rule, env }: { rule: RuleCoverage; env: CheckEnv }) => {
  const { t } = useTranslation("packSpace");
  const { t: tOld } = useTranslation("packOutcome");
  const none = isUncoveredRule(rule);
  const kind = tOld(`rules.kinds.${rule.kind}`, { defaultValue: rule.kind });
  const name =
    rule.rule.origin === "builtin"
      ? `${kind}: ${tOld(`rules.builtin.${rule.rule.builtin ?? ""}`, {
          defaultValue: tOld("rules.builtin.other"),
        })}`
      : kind;
  const Icon = none ? CircleDashed : CircleDot;
  const words = (list: readonly string[]): string =>
    list
      .map((outcome) => t(`check.issues.coverage.outcome.${outcome}`))
      .join(", ");
  const missing = missingOutcomes(rule);
  const place = rule.rule.origin === "manifest" ? rule.rule.file : null;
  return (
    <li className="sp-ck-rule" data-state={none ? "none" : "half"}>
      <p className="sp-ck-finding-head">
        <span className="sp-ck-sev" data-coverage={none ? "none" : "half"}>
          <Icon size="0.875rem" aria-hidden="true" />
          {t(
            none
              ? "check.issues.coverage.stateNone"
              : "check.issues.coverage.stateHalf",
          )}
        </span>
      </p>
      <p className="sp-ck-message">{name}</p>
      <p className="sp-ck-note">
        {rule.seen.length > 0
          ? t("check.issues.coverage.seen", { states: words(rule.seen) })
          : t("check.issues.coverage.seenNone")}{" "}
        {missing.length > 0 &&
          t("check.issues.coverage.missing", { states: words(missing) })}
      </p>
      {rule.witness ? <Witness witness={rule.witness} env={env} /> : null}
      {place !== null ? (
        <div className="sp-ck-actions">
          <button
            type="button"
            className="btn sm"
            onClick={() => {
              env.openFile(place, rule.rule.pointer);
            }}
          >
            {t("check.issues.openPlace")}
          </button>
        </div>
      ) : null}
    </li>
  );
};

/**
 * Какие правила проверены готовыми случаями: процент, сколько правил проверено полностью, частично
 * и совсем не проверено, подсказки «Добавить готовые случаи» и сами правила без полной проверки.
 * Все числа и ситуации приходят в ответе сервера, здесь они только разложены.
 */
export const Coverage = ({
  coverage,
  env,
}: {
  coverage: OutcomeCoverage;
  env: CheckEnv;
}) => {
  const { t } = useTranslation("packSpace");
  const [all, setAll] = useState(false);
  const [open, setOpen] = useState(false);
  const percent = coveragePercent(coverage);
  const rules = [...coverage.rules].sort(
    (a, b) => Number(isUncoveredRule(b)) - Number(isUncoveredRule(a)),
  );
  const shown = all ? rules : rules.slice(0, RULES_SHOWN);
  const rows = coverage.uncovered_rows ?? [];
  const suggest = rows.length > 0 || coverage.scenarios === 0;
  return (
    <section className="sp-ck-card" aria-labelledby="sp-ck-coverage">
      <h3 className="sp-ck-h3" id="sp-ck-coverage">
        {t("check.issues.coverage.title")}
      </h3>
      <div className="sp-ck-percent">
        <span className="sp-ck-percent-num">
          {t("check.issues.coverage.percent", { percent })}
        </span>
        <progress
          className="sp-ck-progress"
          max={100}
          value={percent}
          aria-label={t("check.issues.coverage.percentLabel", { percent })}
        />
      </div>
      {coverage.approximate === true && (
        <p className="sp-ck-note" role="status">
          {t("check.issues.coverage.approximate")}
        </p>
      )}
      <ul className="sp-ck-tally">
        <li data-state="full">
          <CircleCheck size="0.875rem" aria-hidden="true" />
          {t("check.issues.coverage.full", { count: coverage.rules_covered })}
        </li>
        <li data-state="half">
          <CircleDot size="0.875rem" aria-hidden="true" />
          {t("check.issues.coverage.half", { count: coverage.rules_half })}
        </li>
        <li data-state="none">
          <CircleDashed size="0.875rem" aria-hidden="true" />
          {t("check.issues.coverage.none", { count: coverage.rules_uncovered })}
        </li>
      </ul>
      <p className="sp-ck-note">
        {t("check.issues.coverage.cases", { count: coverage.scenarios })}
        {coverage.rows_total !== undefined &&
          coverage.rows_touched !== undefined &&
          ` ${t("check.issues.coverage.variants", {
            touched: coverage.rows_touched,
            total: coverage.rows_total,
          })}`}
      </p>

      {suggest && (
        <div className="sp-ck-suggest">
          <button
            type="button"
            className="btn sm"
            aria-expanded={rows.length > 0 ? open : undefined}
            onClick={() => {
              if (rows.length === 0) env.showSituation({});
              else setOpen(!open);
            }}
          >
            <Plus size="0.8125rem" aria-hidden="true" />
            {rows.length > 0
              ? t("check.issues.coverage.addMany", { count: rows.length })
              : t("check.issues.coverage.addOne")}
          </button>
          {(open || rows.length === 0) && (
            <p className="sp-ck-note">{t("check.issues.coverage.addHow")}</p>
          )}
          {open && rows.length > 0 && (
            <>
              <ul
                className="sp-ck-list"
                aria-label={t("check.issues.coverage.rowsLabel")}
              >
                {rows.slice(0, MAX_ROWS).map((row, index) => (
                  <li key={index} className="sp-ck-rule">
                    <p className="sp-ck-message">
                      <SituationText situation={row.inputs} env={env} />
                    </p>
                    <p className="sp-ck-note">
                      {t("check.issues.coverage.gain", { count: row.gain })}
                    </p>
                    <div className="sp-ck-actions">
                      <button
                        type="button"
                        className="btn sm"
                        onClick={() => {
                          env.showSituation(row.inputs);
                        }}
                      >
                        {t("check.showSituation")}
                      </button>
                    </div>
                  </li>
                ))}
              </ul>
            </>
          )}
        </div>
      )}

      {rules.length > 0 && (
        <div>
          <h4 className="sp-ck-h4">{t("check.issues.coverage.rulesTitle")}</h4>
          <ul className="sp-ck-list">
            {shown.map((rule, index) => (
              <RuleItem
                key={`${rule.rule.file ?? ""}${rule.rule.pointer ?? ""}${rule.rule.builtin ?? ""}${String(index)}`}
                rule={rule}
                env={env}
              />
            ))}
          </ul>
          {!all && rules.length > RULES_SHOWN && (
            <button
              type="button"
              className="btn sm"
              onClick={() => {
                setAll(true);
              }}
            >
              {t("check.showAll", { count: rules.length })}
            </button>
          )}
        </div>
      )}
      {(coverage.rules_omitted ?? 0) > 0 && (
        <p className="sp-ck-note">
          {t("check.issues.coverage.omitted", {
            count: coverage.rules_omitted,
          })}
        </p>
      )}
    </section>
  );
};
