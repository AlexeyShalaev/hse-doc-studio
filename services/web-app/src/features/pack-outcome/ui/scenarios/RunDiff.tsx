import { useTranslation } from "react-i18next";
import type {
  OutcomeChange,
  OutcomeSection,
  PackScenarioRunResult,
} from "@entities/pack-studio";
import { OutcomeSectionSchema } from "@entities/pack-studio";

type RunDiffProps = {
  result: PackScenarioRunResult;
};

const SYMBOL_KEY = { "+": "added", "~": "changed", "-": "removed" } as const;

/** Расхождение по разделам: сначала ожидали и получили, затем список изменений со знаками. */
export const RunDiff = ({ result }: RunDiffProps) => {
  const { t } = useTranslation("packOutcome");
  const bySection = new Map<OutcomeSection, OutcomeChange[]>();
  for (const change of result.changes) {
    const list = bySection.get(change.section) ?? [];
    list.push(change);
    bySection.set(change.section, list);
  }
  return (
    <div className="po-sc-diff" data-testid="scenario-diff">
      {result.failures.length > 0 && (
        <section aria-label={t("scenarios.diff.failures")}>
          <h4 className="po-sc-h">{t("scenarios.diff.failures")}</h4>
          <ul className="po-sc-failures">
            {result.failures.map((failure, index) => (
              <li key={`${String(failure.index)}-${String(index)}`}>
                <p className="po-sc-failure-kind">
                  {failure.index === null
                    ? t("scenarios.diff.snapshot")
                    : t("scenarios.diff.assertion", {
                        n: failure.index + 1,
                        kind: t(`scenarios.kind.${failure.kind}`, {
                          defaultValue: failure.kind,
                        }),
                      })}
                </p>
                <dl className="po-sc-pair">
                  <dt>{t("scenarios.diff.expected")}</dt>
                  <dd>{failure.expected}</dd>
                  <dt>{t("scenarios.diff.actual")}</dt>
                  <dd>{failure.actual}</dd>
                </dl>
                {failure.why.length > 0 && (
                  <p className="po-sc-why">
                    {t("scenarios.diff.why", { rules: failure.why.join(", ") })}
                  </p>
                )}
              </li>
            ))}
          </ul>
        </section>
      )}
      {OutcomeSectionSchema.options
        .filter((section) => bySection.has(section))
        .map((section) => (
          <section key={section} aria-label={t(`sections.${section}`)}>
            <h4 className="po-sc-h">{t(`sections.${section}`)}</h4>
            <ul className="po-sc-changes">
              {(bySection.get(section) ?? []).map((change, index) => (
                <li
                  key={`${change.kind}-${change.id}-${String(index)}`}
                  data-symbol={SYMBOL_KEY[change.symbol]}
                >
                  <span
                    className="po-sc-sign"
                    aria-label={t(
                      `scenarios.diff.${SYMBOL_KEY[change.symbol]}`,
                    )}
                  >
                    {change.symbol}
                  </span>
                  <span className="po-sc-change-text">
                    {change.label}
                    {(change.before !== null || change.after !== null) && (
                      <span className="po-sc-change-values">
                        {change.before !== null && (
                          <>
                            {" "}
                            {t("scenarios.diff.was", { value: change.before })}
                          </>
                        )}
                        {change.after !== null && (
                          <>
                            {" "}
                            {t("scenarios.diff.now", { value: change.after })}
                          </>
                        )}
                      </span>
                    )}
                  </span>
                </li>
              ))}
            </ul>
          </section>
        ))}
    </div>
  );
};
