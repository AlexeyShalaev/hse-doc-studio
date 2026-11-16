import {
  PackOutcomeExplainSchema,
  type OutcomeElementRef,
  type PackOutcome,
  type PackOutcomeExplain,
} from "../api/outcome";
import real from "./explainReal.json";

// «Почему?» на эталонах: подмена API ответа `explain`. Для элементов, у которых есть настоящий ответ
// сервера (explainReal.json: ответы ядра `explain_element` на реальных паках), отдаётся он. Для
// остальных ответ собирается из результата-эталона так же, как это делает ядро: цепочка равна
// `why` элемента, соседи это другие элементы тех же решений, «что если» пусто. Модуль только для
// разработки и тестов (в рабочую сборку не попадает, как и вся подмена).

type RealSet = {
  inputs: Record<string, string>;
  elements: Record<string, unknown>;
};

const REAL = real as unknown as Record<string, RealSet>;

/**
 * Настоящие ответы `explain` для тестов: набор (`vkr`, `vkr_alt`, `coursework`, `coursework_alt`),
 * вводные, на которых они посчитаны, и ответы по ключу `раздел:id`. Ответы разобраны строгой
 * схемой, поэтому расхождение схемы и ответа ядра видно сразу.
 */
export const realExplains = (): {
  set: string;
  inputs: Record<string, string>;
  elements: Record<string, PackOutcomeExplain>;
}[] =>
  Object.entries(REAL).map(([set, value]) => ({
    set,
    inputs: value.inputs,
    elements: Object.fromEntries(
      Object.entries(value.elements).map(([key, body]) => [
        key,
        PackOutcomeExplainSchema.parse(body),
      ]),
    ),
  }));

/** Какой набор настоящих ответов относится к результату: по шаблону и сценарию вводных. */
const setKeyOf = (template: string, inputs: Record<string, string>): string => {
  const base = template === "vkr" ? "vkr" : "coursework";
  const alt = `${base}_alt`;
  const altInputs = REAL[alt]?.inputs;
  if (
    altInputs &&
    Object.entries(altInputs).every(([k, v]) => inputs[k] === v)
  ) {
    return alt;
  }
  return base;
};

type Info = { state: string; why: readonly string[] };

/** Состояние и `why` каждого элемента результата: те же идентификаторы, что у сервера. */
export const elementInfos = (outcome: PackOutcome): Map<string, Info> => {
  const found = new Map<string, Info>();
  const flag = (on: boolean) => (on ? "present" : "absent");
  const put = (section: string, id: string, info: Info) => {
    found.set(`${section}:${id}`, info);
  };
  for (const doc of outcome.documents) {
    put("documents", doc.id, { state: doc.state, why: doc.why });
  }
  for (const field of outcome.meta) {
    put("meta", field.id, { state: flag(field.visible), why: field.why });
  }
  for (const form of outcome.forms) {
    put("forms", form.id, { state: flag(form.applies), why: form.why });
    for (const field of form.fields) {
      put("forms", `${form.id}/${field.id}`, {
        state: flag(field.visible),
        why: field.why,
      });
    }
  }
  for (const person of outcome.participants) {
    put("participants", person.persona, {
      state: flag(person.present),
      why: person.why,
    });
  }
  for (const point of outcome.points) {
    put("points", point.id, { state: "present", why: point.why });
    for (const item of point.items) {
      put("points", `${point.id}/${item.doc_id}`, {
        state: flag(item.active),
        why: item.why,
      });
    }
    for (const extra of point.extra_items) {
      put("points", `${point.id}/${extra.source}`, {
        state: flag(extra.active),
        why: extra.why,
      });
    }
    const route = point.route;
    put("route", point.id, { state: "present", why: route.why });
    route.steps.forEach((step, index) => {
      const personas = new Set(step.map((person) => person.persona));
      const why = [
        ...route.why,
        ...route.pairs
          .filter((pair) => personas.has(pair.persona))
          .flatMap((pair) => pair.why),
      ];
      put("route", `${point.id}/step/${String(index + 1)}`, {
        state: "present",
        why: [...new Set(why)],
      });
    });
    for (const pair of route.pairs) {
      const id =
        pair.persona === pair.slot_id
          ? `${point.id}/${pair.doc_id}/${pair.slot_id}`
          : `${point.id}/${pair.doc_id}/${pair.slot_id}/${pair.persona}`;
      put("route", id, { state: "present", why: pair.why });
    }
    for (const skipped of route.skipped) {
      const key = `route:${point.id}/${skipped.doc_id}/${skipped.slot_id}`;
      if (!found.has(key)) {
        found.set(key, { state: "absent", why: skipped.why });
      }
    }
  }
  for (const rule of outcome.checks ?? []) {
    put("checks", rule.id, { state: flag(rule.enabled), why: rule.why });
  }
  return found;
};

/**
 * Ответ `explain` по результату-эталону; `null`, если элемента в результате нет (сервер в этом
 * случае отвечает 404 `outcome_element_not_found`).
 */
export const explainFor = (
  outcome: PackOutcome,
  element: OutcomeElementRef,
  template: string,
): PackOutcomeExplain | null => {
  const key = `${element.section}:${element.id}`;
  const info = elementInfos(outcome).get(key);
  if (!info) return null;
  const set = REAL[setKeyOf(template, outcome.inputs)];
  const recorded = set?.elements[key];
  if (recorded) return PackOutcomeExplainSchema.parse(recorded);
  const byId = new Map(outcome.trace.map((entry) => [entry.id, entry]));
  const chain = info.why.flatMap((id) => {
    const entry = byId.get(id);
    return entry ? [entry] : [];
  });
  const readers = new Map<string, OutcomeElementRef>();
  for (const entry of chain) {
    for (const subject of entry.subjects) {
      if (subject.section === element.section && subject.id === element.id) {
        continue;
      }
      readers.set(`${subject.section}:${subject.id}`, subject);
    }
  }
  return PackOutcomeExplainSchema.parse({
    element,
    state: info.state,
    chain,
    readers: [...readers.values()].slice(0, 64),
    counterfactuals: [],
  });
};
