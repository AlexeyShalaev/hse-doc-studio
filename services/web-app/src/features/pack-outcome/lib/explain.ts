import type { TFunction } from "i18next";
import type {
  OutcomeInput,
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

export const makeExplainer = (
  t: TFunction<"packOutcome">,
  lang: string,
  outcome: PackOutcome,
  inputs: readonly OutcomeInput[] | undefined,
): Explainer => {
  const byId = new Map<string, OutcomeTrace>(
    outcome.trace.map((x) => [x.id, x]),
  );
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

  const sentence = (trace: OutcomeTrace): string => {
    return trace.terms
      .map((term) => {
        const actualRaw = trace.actual[term.subject];
        const actual =
          actualRaw === undefined || actualRaw === ""
            ? t("reasons.unset")
            : value(term.subject, actualRaw);
        const expected = term.expected
          .map((e) => value(term.subject, e))
          .join(", ");
        return t(`reasons.op.${term.op}`, {
          subject: subject(term.subject),
          actual,
          expected,
        });
      })
      .join("; ");
  };

  const reasons = (why: readonly string[]): string[] => {
    const out: string[] = [];
    for (const id of why) {
      const trace = byId.get(id);
      if (trace?.status !== "not_held" || trace.terms.length === 0) {
        continue;
      }
      const text = sentence(trace);
      if (text && !out.includes(text)) out.push(text);
    }
    return out;
  };

  return { reasons, subject, value };
};
