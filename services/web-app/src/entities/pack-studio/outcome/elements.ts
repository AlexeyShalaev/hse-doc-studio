import type {
  OutcomeElementRef,
  OutcomePoint,
  PackOutcome,
} from "@entities/pack-studio";
import { pickLocalized } from "@shared/lib/i18n/pickLocalized";

// Что за элемент выбран и как он называется: по `раздел:id` и показанному результату. Форматы id
// те же, что строит сервер (core/pack_studio/outcome/points.py, раздел 4.3 дизайна), клиент
// только читает их из ответа. Ничего не вычисляется: нет в ответе, значит остаётся сам id.

export type ElementKind =
  | "document"
  | "meta"
  | "form"
  | "form_field"
  | "participant"
  | "point"
  | "point_item"
  | "point_extra"
  | "route"
  | "route_step"
  | "route_pair"
  | "route_skipped"
  | "check"
  | "unknown";

export type ElementInfo = {
  kind: ElementKind;
  /** Имя элемента для заголовка панели. */
  title: string;
  /** Точка сдачи, к которой относится элемент: «в точке X». */
  point: string | null;
  /** Номер шага маршрута (у остальных элементов null). */
  step?: number;
};

const unknown = (el: OutcomeElementRef): ElementInfo => ({
  kind: "unknown",
  title: el.id,
  point: null,
});

/** Точка, чьим id начинается остаток: самый длинный совпавший id (в id точки бывает косая черта). */
const pointOf = (
  outcome: PackOutcome,
  id: string,
): { point: OutcomePoint; rest: string } | null => {
  let best: OutcomePoint | null = null;
  for (const point of outcome.points) {
    const hit = id === point.id || id.startsWith(`${point.id}/`);
    if (hit && (!best || point.id.length > best.id.length)) best = point;
  }
  return best ? { point: best, rest: id.slice(best.id.length + 1) } : null;
};

export const describeElement = (
  outcome: PackOutcome | undefined,
  el: OutcomeElementRef,
  lang: string,
): ElementInfo => {
  if (!outcome) return unknown(el);
  const name = (dict: Record<string, string>, fallback: string) =>
    pickLocalized(dict, lang, fallback);
  switch (el.section) {
    case "documents": {
      const doc = outcome.documents.find((d) => d.id === el.id);
      return doc
        ? { kind: "document", title: name(doc.name, doc.id), point: null }
        : unknown(el);
    }
    case "meta": {
      const field = outcome.meta.find((f) => f.id === el.id);
      return field
        ? { kind: "meta", title: name(field.label, field.id), point: null }
        : unknown(el);
    }
    case "forms": {
      const form = outcome.forms.find(
        (f) => f.id === el.id || el.id.startsWith(`${f.id}/`),
      );
      if (!form) return unknown(el);
      const title = name(form.title, form.id);
      if (el.id === form.id) return { kind: "form", title, point: null };
      const field = form.fields.find((f) => `${form.id}/${f.id}` === el.id);
      return field
        ? {
            kind: "form_field",
            title: `${title}: ${name(field.label, field.id)}`,
            point: null,
          }
        : unknown(el);
    }
    case "participants": {
      const person = outcome.participants.find((p) => p.persona === el.id);
      return person
        ? {
            kind: "participant",
            title: person.name || person.persona,
            point: null,
          }
        : unknown(el);
    }
    case "points": {
      const found = pointOf(outcome, el.id);
      if (!found) return unknown(el);
      const { point, rest } = found;
      const pointName = name(point.name, point.id);
      if (rest === "") {
        return { kind: "point", title: pointName, point: pointName };
      }
      const item = point.items.find((i) => i.doc_id === rest);
      if (item) {
        const doc = outcome.documents.find((d) => d.id === item.doc_id);
        return {
          kind: "point_item",
          title: doc ? name(doc.name, doc.id) : item.doc_id,
          point: pointName,
        };
      }
      const extra = point.extra_items.find((e) => e.source === rest);
      return extra
        ? { kind: "point_extra", title: extra.output_name, point: pointName }
        : unknown(el);
    }
    case "route": {
      const found = pointOf(outcome, el.id);
      if (!found) return unknown(el);
      const { point, rest } = found;
      const pointName = name(point.name, point.id);
      if (rest === "") {
        return { kind: "route", title: pointName, point: pointName };
      }
      const step = /^step\/(\d+)$/.exec(rest)?.[1];
      if (step) {
        return {
          kind: "route_step",
          title: pointName,
          point: pointName,
          step: Number(step),
        };
      }
      const [doc, slot, persona] = rest.split("/");
      const docName = outcome.documents.find((d) => d.id === doc);
      const title = `${docName ? name(docName.name, docName.id) : (doc ?? rest)}: ${persona ?? slot ?? ""}`;
      const skipped =
        !point.route.pairs.some(
          (pair) =>
            pair.doc_id === doc &&
            pair.slot_id === slot &&
            (persona === undefined
              ? pair.persona === slot
              : pair.persona === persona),
        ) &&
        point.route.skipped.some(
          (pair) => pair.doc_id === doc && pair.slot_id === slot,
        );
      return {
        kind: skipped ? "route_skipped" : "route_pair",
        title,
        point: pointName,
      };
    }
    case "checks": {
      const rule = outcome.checks?.find((c) => c.id === el.id);
      return rule
        ? { kind: "check", title: name(rule.title, rule.id), point: null }
        : unknown(el);
    }
  }
};
