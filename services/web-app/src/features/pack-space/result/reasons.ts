import type { TFunction } from "i18next";
import type {
  OutcomeInput,
  OutcomeTrace,
  PackOutcome,
} from "@entities/pack-studio";
import { pickLocalized } from "@shared/lib/i18n/pickLocalized";

// Причины «не вошло» простыми словами (pack-studio-ux.md, 5.3). Ничего не вычисляется: берутся
// решения, которые сервер уже принял (`status: not_held` в `trace`), и пересказываются фразой
// «вид работы: нужно «исследовательская», сейчас «проектная»». Если условие можно выполнить одной
// сменой условия студента, рядом готово действие «Показать при …» (какое условие и какое значение).

/** Смена одного условия студента, после которой элемент вернётся в результат. */
export type ShowAction = {
  input: string;
  value: string;
  /** Подпись для кнопки: «Работа под NDA: да». */
  label: string;
};

export type Reason = {
  text: string;
  action: ShowAction | null;
};

type T = TFunction<"packSpace">;

const up = (text: string): string =>
  text === "" ? text : text.charAt(0).toUpperCase() + text.slice(1);

const OFF_VALUES = new Set(["no", "none", "false"]);

export type Reasoner = {
  /** Подпись условия или факта (`kind`: «Вид работы»). */
  subject: (id: string) => string;
  /** Подпись значения условия (`kind`, `project`: «проектная»). */
  value: (subject: string, raw: string) => string;
  /** Причина по решениям `why` элемента; `null`, если сервер ничего не вернул. */
  why: (ids: readonly string[]) => Reason | null;
  /** Действие «Показать при …» для условия `input`, чьё значение сейчас выключает элемент. */
  turnOn: (input: string) => ShowAction | null;
};

export const makeReasoner = (
  t: T,
  lang: string,
  outcome: PackOutcome,
  inputs: readonly OutcomeInput[] | undefined,
): Reasoner => {
  const byId = new Map<string, OutcomeTrace>(
    outcome.trace.map((trace) => [trace.id, trace]),
  );
  const input = (id: string) => inputs?.find((item) => item.id === id);
  const lookup = (path: string): string | null =>
    t(path, { defaultValue: "" }) || null;

  const subject = (id: string): string => {
    // `supervisor.role`: организация человека, подпись строится от подписи самого человека.
    const org = /^(.+)\.role$/.exec(id)?.[1];
    if (org && !input(id))
      return t("result.why.orgOf", { subject: subject(org) });
    const found = input(id);
    if (found?.label) return up(pickLocalized(found.label, lang, id));
    return up(lookup(`result.why.subjects.${id}`) ?? id);
  };
  const value = (id: string, raw: string): string => {
    const label = input(id)?.values.find((item) => item.value === raw)?.label;
    if (label) return pickLocalized(label, lang, raw);
    return lookup(`result.why.values.${raw}`) ?? raw;
  };
  const actual = (trace: OutcomeTrace, id: string): string => {
    const raw = trace.actual[id];
    return raw === undefined || raw === ""
      ? t("result.why.unset")
      : value(id, raw);
  };

  const action = (id: string, raw: string): ShowAction => ({
    input: id,
    value: raw,
    label: `${subject(id)}: ${value(id, raw)}`,
  });

  /** Какое значение условия вернёт элемент: первое из нужных, что отличается от текущего. */
  const actionOf = (trace: OutcomeTrace): ShowAction | null => {
    for (const term of trace.terms) {
      const known = input(term.subject);
      if (!known) continue;
      const current = outcome.inputs[term.subject];
      const wanted =
        term.op === "truthy"
          ? known.values.find((item) => !OFF_VALUES.has(item.value))?.value
          : term.expected.find(
              (item) =>
                item !== current &&
                known.values.some((candidate) => candidate.value === item),
            );
      if (wanted !== undefined && wanted !== current) {
        return action(term.subject, wanted);
      }
    }
    return null;
  };

  const sentence = (trace: OutcomeTrace): string =>
    trace.terms
      .map((term) => {
        const key = term.op === "contains_any" ? "contains" : term.op;
        return t(`result.why.${key}`, {
          subject: subject(term.subject),
          actual: actual(trace, term.subject),
          expected: term.expected
            .map((item) => value(term.subject, item))
            .join(", "),
        });
      })
      .join(" ");

  const why = (ids: readonly string[]): Reason | null => {
    const failed = ids
      .map((id) => byId.get(id))
      .filter(
        (trace): trace is OutcomeTrace =>
          trace?.status === "not_held" && trace.terms.length > 0,
      );
    if (failed.length === 0) return null;
    const texts = [...new Set(failed.map(sentence))];
    const found = failed.map(actionOf).find((item) => item !== null) ?? null;
    return { text: texts.join(" "), action: found };
  };

  const turnOn = (id: string): ShowAction | null => {
    const known = input(id);
    if (!known) return null;
    const current = outcome.inputs[id] ?? known.default;
    if (!OFF_VALUES.has(current)) return null;
    const wanted = known.values.find((item) => !OFF_VALUES.has(item.value));
    return wanted ? action(id, wanted.value) : null;
  };

  return { subject, value, why, turnOn };
};
