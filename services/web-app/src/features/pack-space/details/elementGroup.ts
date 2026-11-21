import type { ElementKind } from "@features/pack-outcome/lib/elements";

// Слова о выбранном элементе зависят от того, что это: документ «входит в комплект», поле
// «показывается», участник «участвует». Виды элементов сервера собраны в семь групп, и по группе
// выбираются глаголы в «Почему так», название состояния и пояснения «что изменится».

export type ElementGroup =
  "document" | "field" | "participant" | "item" | "route" | "step" | "check";

const GROUPS: Record<ElementKind, ElementGroup> = {
  document: "document",
  meta: "field",
  form: "field",
  form_field: "field",
  participant: "participant",
  point: "item",
  point_item: "item",
  point_extra: "item",
  route: "route",
  route_pair: "route",
  route_skipped: "route",
  route_step: "step",
  check: "check",
  unknown: "field",
};

export const groupOf = (kind: ElementKind): ElementGroup => GROUPS[kind];

/** Состояние, о котором сервер говорит словами «есть» и «нет» (у документа ещё «выключен»). */
export type ElementState = "active" | "inactive" | "present" | "absent";

export const stateOf = (raw: string): ElementState =>
  raw === "active" || raw === "inactive" || raw === "present" ? raw : "absent";

/** Элемент в результате есть (документ в комплекте, поле показывается). */
export const isIn = (state: ElementState): boolean =>
  state === "active" || state === "present";
