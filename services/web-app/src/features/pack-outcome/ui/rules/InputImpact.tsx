import { useMemo, useState } from "react";
import { ExternalLink } from "lucide-react";
import { Cpu } from "lucide-react";
import { useTranslation } from "react-i18next";
import type {
  OutcomeElementRef,
  OutcomeRuleRef,
  OutcomeSection,
} from "@entities/pack-studio";
import { Badge } from "@shared/ui";
import { describeElement } from "../../lib/elements";
import { makeTraceText } from "../../lib/explain";
import { elementKey, linkedElements } from "../../lib/inputs";
import { readsInput, ruleKey } from "../../lib/rules";
import { useOutcomeModel } from "../../model";
import { useInputLabels } from "../inputs/useLabels";
import { useOpenRule } from "./useOpenRule";

const SHOWN = 6;

type Rule = { key: string; rule: OutcomeRuleRef };

/**
 * Влияние вводной (раздел 3.5, «Влияние поля»): сколько элементов в скольких разделах она
 * меняет и сколько правил манифеста её читают. Числа `affects` и `rules` даёт словарь вводных
 * сервера, названные элементы и места правил берутся из трассы показанного результата
 * (решения, чьи условия читают вводную). Ничего не выдумывается: нет в ответе, нет и в списке.
 */
export const InputImpact = ({ input: id }: { input: string }) => {
  const { t, i18n } = useTranslation("packOutcome");
  const { inputs, shown, select, phone } = useOutcomeModel();
  const { inputLabel } = useInputLabels();
  const open = useOpenRule();
  const [all, setAll] = useState<Set<string>>(new Set());
  const input = inputs.data?.inputs.find((item) => item.id === id);
  const lang = i18n.language;
  const text = useMemo(
    () => makeTraceText(t, lang, inputs.data?.inputs),
    [t, lang, inputs.data],
  );
  const name = input ? inputLabel(input) : text.subject(id);

  const elements = useMemo(() => linkedElements(shown, id), [shown, id]);
  const bySection = useMemo(() => {
    const map = new Map<OutcomeSection, OutcomeElementRef[]>();
    for (const el of elements) {
      const list = map.get(el.section);
      if (list) list.push(el);
      else map.set(el.section, [el]);
    }
    return [...map.entries()];
  }, [elements]);
  const rules = useMemo(() => {
    const seen = new Set<string>();
    const out: Rule[] = [];
    for (const trace of shown?.trace ?? []) {
      if (!readsInput(trace, id)) continue;
      const key = ruleKey(trace.rule);
      if (seen.has(key)) continue;
      seen.add(key);
      out.push({ key, rule: trace.rule });
    }
    return out;
  }, [shown, id]);

  const inert = input?.affects.length === 0;
  const ruleCount = input?.rules ?? rules.length;

  return (
    <div className="po-why" data-testid="outcome-impact">
      <header className="po-why-head">
        <p className="po-rules-label">
          <span className="po-mark">{t("rules.impact.kind")}</span>
        </p>
        <h3 className="po-why-title" data-testid="outcome-why-title">
          {name}
        </h3>
        <p className="po-why-meta">
          <span className="mono po-rules-id" data-testid="outcome-selected">
            {id}
          </span>
          {shown?.inputs[id] !== undefined && (
            <Badge variant="accent">
              {text.value(id, shown.inputs[id] ?? "")}
            </Badge>
          )}
        </p>
      </header>

      {inputs.data === undefined || shown === undefined ? (
        <p className="po-note" data-testid="outcome-impact-wait">
          {t("rules.impact.wait")}
        </p>
      ) : input === undefined ? (
        <p className="po-calm" data-testid="outcome-impact-unknown">
          {t("rules.impact.unknown")}
        </p>
      ) : inert ? (
        <p className="po-calm" data-testid="outcome-impact-inert">
          {t("rules.impact.inert")}
        </p>
      ) : (
        <p className="po-impact-sum" data-testid="outcome-impact-summary">
          {[
            t("rules.impact.elements", { count: elements.length }),
            t("rules.impact.sections", {
              count: bySection.length || input.affects.length,
            }),
            t("rules.impact.rulesRead", { count: ruleCount }),
          ].join(", ")}
        </p>
      )}

      {input && !inert && elements.length === 0 && shown && (
        <p className="po-note" data-testid="outcome-impact-nolinks">
          {t("rules.impact.noLinks", {
            sections: input.affects.map((s) => t(`sections.${s}`)).join(", "),
          })}
        </p>
      )}

      {bySection.map(([section, list]) => {
        const expanded = all.has(section);
        const items = expanded ? list : list.slice(0, SHOWN);
        return (
          <section
            key={section}
            className="po-rules-block"
            data-testid={`outcome-impact-${section}`}
            aria-label={t(`sections.${section}`)}
          >
            <h3 className="po-rules-sub">
              {t(`sections.${section}`)}
              <span className="po-group-count">{list.length}</span>
            </h3>
            <ul className="po-readers">
              {items.map((el) => {
                const info = describeElement(shown, el, lang);
                return (
                  <li key={elementKey(el)}>
                    <button
                      type="button"
                      className="po-reader"
                      data-testid={`outcome-impact-el-${el.section}-${el.id}`}
                      onClick={() => {
                        select(el);
                      }}
                    >
                      <span className="po-reader-title">
                        {info.kind === "route_step"
                          ? t("rules.stepTitle", {
                              n: info.step ?? 0,
                              point: info.point ?? "",
                            })
                          : info.title}
                      </span>
                    </button>
                  </li>
                );
              })}
            </ul>
            {list.length > SHOWN && (
              <button
                type="button"
                className="po-link"
                aria-expanded={expanded}
                onClick={() => {
                  setAll((prev) => {
                    const next = new Set(prev);
                    if (expanded) next.delete(section);
                    else next.add(section);
                    return next;
                  });
                }}
              >
                {expanded
                  ? t("rules.readers.less")
                  : t("rules.readers.more", { count: list.length - SHOWN })}
              </button>
            )}
          </section>
        );
      })}

      {rules.length > 0 && (
        <section
          className="po-rules-block"
          aria-labelledby="po-impact-rules"
          data-testid="outcome-impact-rules"
        >
          <h3 className="po-rules-sub" id="po-impact-rules">
            {t("rules.impact.rules")}
            <span className="po-group-count">{rules.length}</span>
          </h3>
          {input && rules.length < input.rules && (
            <p className="po-note">
              {t("rules.impact.rulesHere", {
                here: rules.length,
                total: input.rules,
              })}
            </p>
          )}
          <ul className="po-impact-rules">
            {rules.map(({ key, rule }, index) => {
              const where = open.locate(rule);
              return (
                <li
                  key={key}
                  className="po-impact-rule"
                  data-testid={`outcome-impact-rule-${String(index)}`}
                >
                  {rule.origin === "builtin" ? (
                    <span className="po-chain-origin">
                      <Badge variant="info">
                        <Cpu size="0.75rem" aria-hidden="true" />
                        {t("rules.inEngine")}
                      </Badge>
                      <span className="po-note">
                        {t(`rules.builtin.${rule.builtin ?? ""}`, {
                          defaultValue: t("rules.builtin.other"),
                        })}
                      </span>
                    </span>
                  ) : (
                    <>
                      <span className="po-mono">
                        {rule.file}
                        <span className="po-chain-pointer">{rule.pointer}</span>
                      </span>
                      {where && !phone && (
                        <button
                          type="button"
                          className="btn sm"
                          data-testid={`outcome-impact-rule-${String(index)}-open`}
                          onClick={() => {
                            open.open(rule);
                          }}
                        >
                          <ExternalLink size="0.75rem" aria-hidden="true" />
                          {t("rules.openRule")}
                        </button>
                      )}
                    </>
                  )}
                </li>
              );
            })}
          </ul>
        </section>
      )}
    </div>
  );
};
