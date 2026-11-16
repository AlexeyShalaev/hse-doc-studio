import type { TFunction } from "i18next";
import type {
  OutcomeInput,
  OutcomeTerm,
  OutcomeTrace,
  PackOutcome,
} from "@entities/pack-studio";
import { pickLocalized } from "@shared/lib/i18n/pickLocalized";

/**
 * Человеческий текст причины из трассы ответа сервера. Ничего не вычисляет: берёт решения,
 * которые сервер уже принял (`status: not_held`), и пересказывает условие словами по его
 * операции (`in`, `equals`, `contains_any`, `present`, `truthy`) и фактическому значению.
 */
export type Explainer = {
  /** Тексты невыполненных условий среди решений `why` элемента; пусто, если причин нет. */
  reasons: (why: readonly string[]) => string[];
  /** Подпись вводной или значения для текста (`kind` -> «вид работы»). */
  subject: (id: string) => string;
  value: (subject: string, value: string) => string;
};

const lookup = (
  t: TFunction<"packOutcome">,
  group: "subjects" | "values",
  key: string,
): string | null => {
  const path = `reasons.${group}.${key}`;
  return t(path, { defaultValue: "" }) || null;
};

/** Тексты условий и фактов решений трассы: ровно то, что вернул сервер, словами. */
export type TraceText = {
  /** Подпись вводной или значения для текста (`kind` -> «вид работы»). */
  subject: (id: string) => string;
  value: (subject: string, value: string) => string;
  /** Условие решения человеческой фразой («вид работы: проектный») по всем его терминам. */
  condition: (trace: OutcomeTrace) => string;
  /** Что вычислитель увидел: пары «предмет, значение» из `actual`. */
  facts: (trace: OutcomeTrace) => { subject: string; value: string }[];
  /** Фраза о невыполненном условии («вид работы: сейчас проектный, нужно исследовательский»). */
  failure: (trace: OutcomeTrace) => string;
};

export const makeTraceText = (
  t: TFunction<"packOutcome">,
  lang: string,
  inputs: readonly OutcomeInput[] | undefined,
): TraceText => {
  const input = (id: string) => inputs?.find((i) => i.id === id);

  const subject = (id: string): string => {
    // `supervisor.role`: организация человека, подпись строится от подписи самого человека.
    const org = /^(.+)\.role$/.exec(id)?.[1];
    if (org && !input(id)) {
      return t("reasons.orgOf", { subject: subject(org) });
    }
    const found = input(id);
    if (found?.label) return pickLocalized(found.label, lang, id);
    return lookup(t, "subjects", id) ?? id;
  };
  const value = (id: string, raw: string): string => {
    const label = input(id)?.values.find((v) => v.value === raw)?.label;
    if (label) return pickLocalized(label, lang, raw);
    return lookup(t, "values", raw) ?? raw;
  };
  const actualOf = (trace: OutcomeTrace, id: string): string => {
    const raw = trace.actual[id];
    return raw === undefined || raw === ""
      ? t("reasons.unset")
      : value(id, raw);
  };
  const expectedOf = (term: OutcomeTerm): string =>
    term.expected.map((e) => value(term.subject, e)).join(", ");

  const failure = (trace: OutcomeTrace): string =>
    trace.terms
      .map((term) =>
        t(`reasons.op.${term.op}`, {
          subject: subject(term.subject),
          actual: actualOf(trace, term.subject),
          expected: expectedOf(term),
        }),
      )
      .join("; ");

  const condition = (trace: OutcomeTrace): string =>
    trace.terms
      .map((term) =>
        t(`rules.cond.${term.op}`, {
          subject: subject(term.subject),
          expected: expectedOf(term),
        }),
      )
      .join(t(trace.join === "any" ? "rules.joinAny" : "rules.joinAll"));

  const facts = (trace: OutcomeTrace) =>
    Object.entries(trace.actual).map(([id, raw]) => ({
      subject: subject(id),
      value: raw === "" ? t("reasons.unset") : value(id, raw),
    }));

  return { subject, value, condition, facts, failure };
};

export const makeExplainer = (
  t: TFunction<"packOutcome">,
  lang: string,
  outcome: PackOutcome,
  inputs: readonly OutcomeInput[] | undefined,
): Explainer => {
  const byId = new Map<string, OutcomeTrace>(
    outcome.trace.map((x) => [x.id, x]),
  );
  const text = makeTraceText(t, lang, inputs);

  const reasons = (why: readonly string[]): string[] => {
    const out: string[] = [];
    for (const id of why) {
      const trace = byId.get(id);
      if (trace?.status !== "not_held" || trace.terms.length === 0) {
        continue;
      }
      const sentence = text.failure(trace);
      if (sentence && !out.includes(sentence)) out.push(sentence);
    }
    return out;
  };

  return { reasons, subject: text.subject, value: text.value };
};
