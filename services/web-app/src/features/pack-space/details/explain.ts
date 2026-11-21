import type { TFunction } from "i18next";
import type {
  OutcomeTerm,
  OutcomeTrace,
  PackOutcomeExplain,
} from "@entities/pack-studio";
import { stateOf, type ElementGroup, type ElementState } from "./elementGroup";
import { sentence, soft, type Words } from "./words";

// «Почему так» человеческим языком. Сервер отвечает цепочкой решений (`chain`): правило, его
// условие, что вычислитель увидел и выполнено ли оно. Здесь каждое решение пересказывается одним
// предложением («Вид работы: проектная. Входит в комплект, когда вид работы: проектная.»).
// Ничего не вычисляется: берутся решения сервера, слова берутся из словаря области.

/** `ok`: условие работает в пользу элемента, `no`: против, `skip`: не проверялось, `info`: без исхода. */
export type SentenceTone = "ok" | "no" | "skip" | "info";

export type Sentence = {
  /** Номер решения в ответе: ключ списка. */
  id: string;
  tone: SentenceTone;
  /** «Вид работы: проектная»: что вычислитель увидел. */
  facts: { label: string; value: string }[];
  /** Вывод: «Входит в комплект, когда вид работы: проектная.» */
  text: string;
  /** Правило зашито в Студию: поменять его по месту нельзя. */
  builtin: boolean;
};

export type ExplainContext = {
  t: TFunction;
  words: Words;
  group: ElementGroup;
};

const quote = (t: TFunction, text: string): string =>
  t("details.why.quote", { text });

const joinOr = (t: TFunction, items: readonly string[]): string => {
  if (items.length < 2) return items[0] ?? "";
  return `${items.slice(0, -1).join(", ")} ${t("details.why.or")} ${items.at(-1) ?? ""}`;
};

/** Условие одного термина: «вид работы: проектная или исследовательская». */
const needOf = (term: OutcomeTerm, { t, words }: ExplainContext): string => {
  const subject = words.subject(term.subject);
  const values = term.expected.map((raw) => words.value(term.subject, raw));
  switch (term.op) {
    case "in":
    case "equals":
      return t("details.why.need.in", {
        subject: soft(subject),
        values: joinOr(t, values.map(soft)),
      });
    case "contains_any":
      return t("details.why.need.contains", {
        subject,
        values: joinOr(
          t,
          values.map((value) => quote(t, value)),
        ),
      });
    case "present":
      return t("details.why.need.present", { subject: soft(subject) });
    case "truthy":
      return t("details.why.need.truthy", { subject: soft(subject) });
  }
};

const conditionOf = (trace: OutcomeTrace, ctx: ExplainContext): string =>
  trace.terms
    .map((term) => needOf(term, ctx))
    .join(ctx.t(trace.join === "any" ? "details.why.any" : "details.why.all"));

const factsOf = (
  trace: OutcomeTrace,
  { t, words }: ExplainContext,
): Sentence["facts"] =>
  Object.entries(trace.actual).map(([id, raw]) => ({
    label: sentence(words.subject(id)),
    value: raw === "" ? t("details.why.unset") : words.value(id, raw),
  }));

const toneOf = (trace: OutcomeTrace): SentenceTone => {
  if (trace.status === "skipped") return "skip";
  if (trace.terms.length === 0) return "info";
  const held = trace.status === "held";
  switch (trace.effect) {
    case "exclude":
      return held ? "no" : "ok";
    case "require":
    case "order":
      return "info";
    case "gate":
    case "add":
    case "display":
      return held ? "ok" : "no";
  }
};

/** Языки: условие «язык из списка» читается как «редакции есть на языках». */
const LANG_KINDS = new Set(["supported_langs", "variant_langs"]);

const verdictOf = (trace: OutcomeTrace, ctx: ExplainContext): string => {
  const { t, words, group } = ctx;
  if (trace.status === "skipped") return t("details.why.skipped");
  const state = trace.status;
  if (trace.terms.length === 0) {
    return t(`details.why.static.${trace.kind}.${state}`, {
      defaultValue: t(`details.why.static.other.${state}`),
    });
  }
  const first = trace.terms[0];
  if (LANG_KINDS.has(trace.kind) && first) {
    return t(`details.why.langs.${trace.kind}.${state}`, {
      values: first.expected
        .map((raw) => words.value(first.subject, raw))
        .join(", "),
    });
  }
  return t(`details.why.verdict.${trace.effect}.${state}`, {
    in: sentence(t(`details.verb.${group}.in`)),
    out: sentence(t(`details.verb.${group}.out`)),
    need: conditionOf(trace, ctx),
  });
};

/** Что за правило зашито в Студию: пояснение под предложением. */
const builtinNote = (trace: OutcomeTrace, t: TFunction): string =>
  trace.rule.origin === "builtin"
    ? t(`details.why.builtin.${trace.rule.builtin ?? "other"}`, {
        defaultValue: t("details.why.builtin.other"),
      })
    : "";

/**
 * Цепочка решений сервера человеческими предложениями: по одному на решение, повторы убраны,
 * порядок сервера сохранён. Для всех видов правил (виды работы, состав, языки, видимость поля,
 * условие подписи, пропуск при NDA, необязательность, отключённые проверки, правила Студии).
 */
export const explainToSentences = (
  chain: readonly OutcomeTrace[],
  ctx: ExplainContext,
): Sentence[] => {
  const seen = new Set<string>();
  const out: Sentence[] = [];
  for (const trace of chain) {
    const facts = factsOf(trace, ctx);
    const note = builtinNote(trace, ctx.t);
    const text = [verdictOf(trace, ctx), note].filter(Boolean).join(" ");
    const key = `${facts.map((f) => `${f.label}=${f.value}`).join("|")}#${text}`;
    if (seen.has(key)) continue;
    seen.add(key);
    out.push({
      id: trace.id,
      tone: toneOf(trace),
      facts,
      text,
      builtin: trace.rule.origin === "builtin",
    });
  }
  return out;
};

export type WhatIfRow = {
  input: string;
  value: string;
  /** «Вид работы» и «исследовательская»: подписи для кнопки. */
  inputLabel: string;
  valueLabel: string;
  /** Что будет с элементом: «документа не будет». */
  text: string;
  result: ElementState;
};

/**
 * «Что изменится, если…»: из соседних значений условий, которые сервер пересчитал, остаются те,
 * что реально меняют элемент (текущее значение и тот же исход не показываются).
 */
export const whatIfRows = (
  explain: Pick<PackOutcomeExplain, "state" | "counterfactuals">,
  current: Readonly<Record<string, string>> | undefined,
  { t, words, group }: ExplainContext,
): WhatIfRow[] => {
  const now = stateOf(explain.state);
  return explain.counterfactuals
    .filter(
      (cf) => current?.[cf.input] !== cf.value && stateOf(cf.result) !== now,
    )
    .map((cf) => {
      const result = stateOf(cf.result);
      return {
        input: cf.input,
        value: cf.value,
        inputLabel: sentence(words.subject(cf.input)),
        valueLabel: words.value(cf.input, cf.value),
        text: t(`details.whatIf.result.${group}.${result}`),
        result,
      };
    });
};
