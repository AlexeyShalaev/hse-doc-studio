import type {
  OutcomeElementRef,
  OutcomeSection,
  PackOutcome,
} from "@entities/pack-studio";
import { pickLocalized } from "@shared/lib/i18n/pickLocalized";
import { extraId, itemId, pairId, pointId, stepId } from "../routeIds";

// Что поменялось в результате после правки: сравнение двух ответов сервера (до и после).
// Это не расчёт правил: клиент не знает, почему элемент появился, он видит, что в ответе он был
// или не был, был включён или выключен. Знаки те же, что у «До и после»: `+` появился или
// включился, `-` исчез или выключился, `~` остался, но изменился. Точный `impact` и `compare`
// сервера (срез O7) заменит это сравнение, когда придёт.

export type DeltaSymbol = "+" | "~" | "-";

export type DeltaItem = {
  symbol: DeltaSymbol;
  section: OutcomeSection;
  id: string;
  label: string;
  /** Было и стало словами, где они есть (`~`). */
  before: string | null;
  after: string | null;
};

type Row = { label: string; on: boolean; detail: string };
type Table = Map<string, Row>;

const diffTables = (
  section: OutcomeSection,
  before: Table,
  after: Table,
): DeltaItem[] => {
  const out: DeltaItem[] = [];
  const ids = new Set([...before.keys(), ...after.keys()]);
  for (const id of ids) {
    const was = before.get(id);
    const now = after.get(id);
    const wasOn = was?.on ?? false;
    const nowOn = now?.on ?? false;
    const label = (now ?? was)?.label ?? id;
    if (!wasOn && nowOn) {
      out.push({
        symbol: "+",
        section,
        id,
        label,
        before: null,
        after: now?.detail ?? null,
      });
    } else if (wasOn && !nowOn) {
      out.push({
        symbol: "-",
        section,
        id,
        label,
        before: was?.detail ?? null,
        after: null,
      });
    } else if (wasOn && nowOn && was?.detail !== now?.detail) {
      out.push({
        symbol: "~",
        section,
        id,
        label,
        before: was?.detail ?? null,
        after: now?.detail ?? null,
      });
    }
  }
  return out;
};

const tablesOf = (outcome: PackOutcome, lang: string) => {
  const name = (dict: Record<string, string>, fallback: string) =>
    pickLocalized(dict, lang, fallback);
  const documents: Table = new Map();
  for (const doc of outcome.documents) {
    const chosen = doc.variants.find((v) => v.chosen)?.id ?? "";
    documents.set(doc.id, {
      label: name(doc.name, doc.id),
      on: doc.state === "active",
      detail: `${chosen}|${doc.lang_state}|${doc.languages.join(",")}`,
    });
  }
  const meta: Table = new Map();
  for (const field of outcome.meta) {
    meta.set(field.id, {
      label: name(field.label, field.id),
      on: field.visible,
      detail: field.required_at,
    });
  }
  const forms: Table = new Map();
  for (const form of outcome.forms) {
    const title = name(form.title, form.id);
    forms.set(form.id, { label: title, on: form.applies, detail: "" });
    for (const field of form.fields) {
      forms.set(`${form.id}/${field.id}`, {
        label: `${title}: ${name(field.label, field.id)}`,
        on: field.visible,
        detail: field.required ? "required" : "",
      });
    }
  }
  const participants: Table = new Map();
  for (const person of outcome.participants) {
    participants.set(person.persona, {
      label: person.name || person.persona,
      on: person.present,
      detail: person.role,
    });
  }
  const points: Table = new Map();
  const route: Table = new Map();
  for (const point of outcome.points) {
    const pointName = name(point.name, point.id);
    points.set(pointId(point.id), { label: pointName, on: true, detail: "" });
    for (const item of point.items) {
      points.set(itemId(point.id, item.doc_id), {
        label: `${pointName}: ${item.doc_id}`,
        on: item.active,
        detail: item.signatures.join(","),
      });
    }
    for (const extra of point.extra_items) {
      points.set(extraId(point.id, extra.source), {
        label: `${pointName}: ${extra.output_name}`,
        on: extra.active,
        detail: extra.format ?? "",
      });
    }
    point.route.steps.forEach((step, index) => {
      route.set(stepId(point.id, index + 1), {
        label: `${pointName}: ${String(index + 1)}`,
        on: step.length > 0,
        detail: step.map((p) => p.persona).join(", "),
      });
    });
    for (const pair of point.route.pairs) {
      route.set(pairId(point.id, pair.doc_id, pair.slot_id, pair.persona), {
        label: `${pointName}: ${pair.doc_id}, ${pair.persona}`,
        on: true,
        detail: pair.optional ? "optional" : "",
      });
    }
  }
  const checks: Table = new Map();
  for (const rule of outcome.checks ?? []) {
    checks.set(rule.id, {
      label: name(rule.title, rule.id),
      on: rule.enabled,
      detail: rule.severity,
    });
  }
  return { documents, meta, forms, participants, points, route, checks };
};

/** Список изменений между двумя результатами; пустой, если структура та же. */
export const diffOutcomes = (
  before: PackOutcome,
  after: PackOutcome,
  lang: string,
): DeltaItem[] => {
  if (before.fingerprint === after.fingerprint) return [];
  const a = tablesOf(before, lang);
  const b = tablesOf(after, lang);
  return (Object.keys(a) as (keyof typeof a)[]).flatMap((section) =>
    diffTables(section, a[section], b[section]),
  );
};

export const deltaElement = (item: DeltaItem): OutcomeElementRef => ({
  section: item.section,
  id: item.id,
});

export type DeltaTally = { added: number; changed: number; removed: number };

export const tallyDelta = (items: readonly DeltaItem[]): DeltaTally => ({
  added: items.filter((i) => i.symbol === "+").length,
  changed: items.filter((i) => i.symbol === "~").length,
  removed: items.filter((i) => i.symbol === "-").length,
});
