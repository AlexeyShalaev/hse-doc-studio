import { useContext, useId, useMemo, useState } from "react";
import { Cpu, ExternalLink, FileCode } from "lucide-react";
import { useTranslation } from "react-i18next";
import type { OutcomeChange } from "@entities/pack-studio";
import { Badge } from "@shared/ui";
import { changeKey, reasonTrace } from "@entities/pack-studio/outcome/compare";
import { makeTraceText } from "@entities/pack-studio/outcome/explain";
import { DecisionStatus } from "./StateChip";
import { useChangeEnv } from "./changeEnv";
import { ChangeWordsContext } from "./changeWords";
import "./styles";

const SYMBOL_KEY = { "+": "added", "~": "changed", "-": "removed" } as const;

type ChangeListProps = {
  changes: readonly OutcomeChange[];
  /** С причинами `why` (сравнение): у изменения кнопка «Почему?» раскрывает правила. */
  withWhy?: boolean;
  testId?: string;
};

/**
 * Изменения одного раздела: знак (`+`, `~`, `-`) вместе со словом и значком не только цветом, подпись
 * элемента и «было» и «стало» двумя колонками у тех, у кого они есть. Причины раскрываются по кнопке
 * (`aria-expanded`), чтобы список читался подряд и с клавиатуры.
 */
export const ChangeList = ({
  changes,
  withWhy = false,
  testId = "outcome-change-list",
}: ChangeListProps) => {
  const { t } = useTranslation("packOutcome");
  const plainWords = useContext(ChangeWordsContext);
  return (
    <ul className="cmp-changes" data-testid={testId}>
      {changes.map((change, index) => {
        const symbol = SYMBOL_KEY[change.symbol];
        const plain = plainWords?.words(change) ?? null;
        const beforeText = plain ? plain.before : change.before;
        const afterText = plain ? plain.after : change.after;
        return (
          <li
            key={changeKey(change, index)}
            className="cmp-change"
            data-symbol={symbol}
            data-testid={`outcome-change-${change.kind}`}
          >
            <span className="cmp-sign">
              <span aria-hidden="true" className="cmp-sign-mark">
                {change.symbol}
              </span>
              <span className="cmp-sign-word">
                {t(`scenarios.diff.${symbol}`)}
              </span>
            </span>
            <div className="cmp-change-body">
              <p className="cmp-change-label">{plain?.label ?? change.label}</p>
              {(change.before !== null || change.after !== null) && (
                <dl className="cmp-values">
                  <div className="cmp-value" data-side="before">
                    <dt>{t("modes.compare.left")}</dt>
                    <dd>
                      {change.before === null
                        ? t("modes.compare.absent")
                        : beforeText === null
                          ? "—"
                          : t("scenarios.diff.was", { value: beforeText })}
                    </dd>
                  </div>
                  <div className="cmp-value" data-side="after">
                    <dt>{t("modes.compare.right")}</dt>
                    <dd>
                      {change.after === null
                        ? t("modes.compare.absent")
                        : afterText === null
                          ? "—"
                          : t("scenarios.diff.now", { value: afterText })}
                    </dd>
                  </div>
                </dl>
              )}
              {withWhy && (change.why?.length ?? 0) > 0 && (
                <ChangeWhy change={change} />
              )}
              {plain && plainWords && plain.tech.length > 0 && (
                <details className="cmp-tech">
                  <summary>{plainWords.techSummary}</summary>
                  <dl>
                    {plain.tech.map((row) => (
                      <div key={row.label}>
                        <dt>{row.label}</dt>
                        <dd>{row.value}</dd>
                      </div>
                    ))}
                  </dl>
                </details>
              )}
            </div>
          </li>
        );
      })}
    </ul>
  );
};

const ChangeWhy = ({ change }: { change: OutcomeChange }) => {
  const { t, i18n } = useTranslation("packOutcome");
  const { inputs, phone, locate, open: openRule } = useChangeEnv();
  const [open, setOpen] = useState(false);
  const panel = useId();
  const text = useMemo(
    () => makeTraceText(t, i18n.language, inputs),
    [t, i18n.language, inputs],
  );
  const reasons = change.why ?? [];
  const word = (value: "held" | "not_held" | "skipped" | null) =>
    value === null ? (
      <Badge variant="subtle">{t("modes.compare.noDecision")}</Badge>
    ) : (
      <DecisionStatus status={value} />
    );
  const facts = (actual: Record<string, string>) =>
    Object.entries(actual).map(([id, raw]) => (
      <span key={id} className="po-fact">
        {text.subject(id)}:{" "}
        <b>{raw === "" ? t("reasons.unset") : text.value(id, raw)}</b>
      </span>
    ));

  return (
    <div className="cmp-why">
      <button
        type="button"
        className="po-link"
        aria-expanded={open}
        aria-controls={panel}
        data-testid="outcome-change-why"
        onClick={() => {
          setOpen(!open);
        }}
      >
        {open ? t("modes.compare.whyHide") : t("modes.compare.why")}
      </button>
      {open && (
        <ol
          id={panel}
          className="cmp-reasons"
          data-testid="outcome-change-reasons"
        >
          {reasons.map((reason, index) => {
            const trace = reasonTrace(reason, "after", index);
            const where = locate(reason.rule);
            return (
              <li
                key={`${reason.kind}-${String(index)}`}
                className="cmp-reason"
              >
                <p className="cmp-reason-kind">
                  {t(`rules.kinds.${reason.kind}`, {
                    defaultValue: reason.kind,
                  })}
                </p>
                <p className="po-chain-cond">
                  {reason.terms.length > 0
                    ? text.condition(trace)
                    : t("rules.noTerms")}
                </p>
                <p className="cmp-reason-sides">
                  <span>
                    {t("modes.compare.left")} {word(reason.before)}
                  </span>
                  <span>
                    {t("modes.compare.right")} {word(reason.after)}
                  </span>
                </p>
                {(Object.keys(reason.before_actual).length > 0 ||
                  Object.keys(reason.after_actual).length > 0) && (
                  <p className="cmp-reason-facts">
                    {Object.keys(reason.before_actual).length > 0 && (
                      <span>
                        <span className="po-note">
                          {t("modes.compare.left")}:
                        </span>{" "}
                        {facts(reason.before_actual)}
                      </span>
                    )}
                    {Object.keys(reason.after_actual).length > 0 && (
                      <span>
                        <span className="po-note">
                          {t("modes.compare.right")}:
                        </span>{" "}
                        {facts(reason.after_actual)}
                      </span>
                    )}
                  </p>
                )}
                {reason.rule.origin === "builtin" ? (
                  <p className="po-chain-origin">
                    <Badge variant="info">
                      <Cpu size="0.75rem" aria-hidden="true" />
                      {t("rules.inEngine")}
                    </Badge>
                  </p>
                ) : (
                  <p className="po-chain-origin">
                    <span className="po-mono po-chain-where">
                      <FileCode size="0.75rem" aria-hidden="true" />
                      <span>
                        {reason.rule.file}
                        <span className="po-chain-pointer">
                          {reason.rule.pointer}
                        </span>
                      </span>
                    </span>
                    {where && openRule && !phone && (
                      <button
                        type="button"
                        className="btn sm"
                        data-testid="outcome-change-open-rule"
                        onClick={() => {
                          openRule(reason.rule);
                        }}
                      >
                        <ExternalLink size="0.75rem" aria-hidden="true" />
                        {t("rules.openRule")}
                      </button>
                    )}
                  </p>
                )}
              </li>
            );
          })}
        </ol>
      )}
    </div>
  );
};
