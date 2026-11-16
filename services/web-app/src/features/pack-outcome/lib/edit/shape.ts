import type { RuleShape } from "@features/pack-forms/rule";

// Какие записи манифеста экран правит по месту и что считается «записью правила» целиком.
// Указатели строит сервер (core/pack_studio/outcome); здесь они только распознаются по хвосту.

const LIST_KEYS: Record<string, "kinds" | "staffing" | "langs"> = {
  supported_kinds: "kinds",
  supported_staffing: "staffing",
  supported_langs: "langs",
};

/** Вид записи для мини-формы; `null`, если запись по месту не правится (остаётся «Открыть правило»). */
export const shapeOf = (pointer: string): RuleShape | null => {
  const tail = pointer.slice(pointer.lastIndexOf("/") + 1);
  const list = LIST_KEYS[tail];
  if (list) return { kind: "list", list };
  switch (tail) {
    case "skip_if_nda":
    case "optional":
      return { kind: "flag", flag: tail };
    case "visible_if":
      return { kind: "visibleIf" };
    case "when":
      return /\/signing_slots\/\d+\/when$/.test(pointer)
        ? { kind: "when" }
        : null;
    case "disabled":
      return pointer === "/checks_version/disabled"
        ? { kind: "checks", list: "disabled" }
        : null;
    case "disabled_categories":
      return pointer === "/checks_version/disabled_categories"
        ? { kind: "checks", list: "categories" }
        : null;
    case "signing_route":
      return { kind: "route" };
    case "route":
      return pointer === "/signatures/route" ? { kind: "route" } : null;
    default:
      return null;
  }
};

/** Запись можно изменить в мини-форме (маршрут целиком правится во вкладке «Форма»). */
export const isEditableShape = (shape: RuleShape | null): boolean =>
  shape !== null && shape.kind !== "route";

export type RecordKind = "slot" | "item" | "extra";

export type RuleRecord = {
  kind: RecordKind;
  /** Указатель записи целиком (слот, пункт точки, дополнительный файл). */
  pointer: string;
  /** Указатель списка, в котором она лежит, и индекс в нём. */
  list: string;
  index: number;
};

const RECORD =
  /^(\/pack_submission\/profiles\/\d+\/(signing_slots|items|extra_items))\/(\d+)(?:\/|$)/;

/** Запись правила, которой принадлежит указатель: слот подписи, пункт точки, дополнительный файл. */
export const recordOf = (pointer: string): RuleRecord | null => {
  const match = RECORD.exec(pointer);
  if (!match) return null;
  const [, list = "", name = "", index = "0"] = match;
  return {
    kind:
      name === "signing_slots" ? "slot" : name === "items" ? "item" : "extra",
    pointer: `${list}/${index}`,
    list,
    index: Number(index),
  };
};

/** Указатель из `base` или вложенный в него. */
export const isUnder = (pointer: string, base: string): boolean =>
  pointer === base || pointer.startsWith(`${base}/`);
