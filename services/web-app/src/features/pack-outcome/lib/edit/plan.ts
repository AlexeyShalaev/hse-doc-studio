import type { PackYamlOp } from "@entities/pack-studio";
import type { RuleChange } from "@features/pack-forms/rule";
import { resolvePointer, sameData, type YamlPath } from "./pointer";
import type { RuleRecord } from "./shape";

// Правка записи манифеста с обратной: «что записать» и «как вернуть» считаются по данным модели
// до записи. Обратная правка это исходное значение записи (набор, условие, ключ или вся запись
// слота, пункта). Откат пишет её тем же слоем точечных правок YAML с If-Match.

/** Что должно быть в манифесте: запись или длина списка. */
export type Guard =
  | { kind: "record"; pointer: string; exists: boolean; value: unknown }
  | { kind: "length"; pointer: string; length: number };

/** Правка по месту: одно изменение записи правила. */
export type RuleEdit = {
  id: string;
  /** Манифест от каталога версии: `version.yaml` или `files/<документ>/doc.yaml`. */
  file: string;
  /** Запись, которую правили (место правила). */
  pointer: string;
  /** `set` значение, `remove` убрать ключ, `delete` убрать запись целиком (слот, пункт). */
  action: "set" | "remove" | "delete";
  /** Вид решения (`slot_when`) или записи (`slot`, `item`) для подписи в ленте. */
  subject: string;
  /** Короткое место: документ и слот, документ, поле. */
  place: string;
  forward: PackYamlOp[];
  inverse: PackYamlOp[];
  /** Состояние манифеста до правки (нужно перед «повторить»). */
  before: Guard;
  /** Состояние после правки (нужно перед «отменить»). */
  after: Guard;
  at: number;
};

/** Чьё это изменение: вид решения и место для ленты правок. */
export type EditLabel = { subject: string; place: string };

export type Planned =
  | { ok: true; edit: Omit<RuleEdit, "id" | "at"> }
  | { ok: false; reason: "missing" | "unchanged" };

const setOp = (path: YamlPath, value: unknown): PackYamlOp => ({
  op: "set",
  path,
  value,
});

/** Значение записи или запись целиком. Манифест не прочитан по указателю: `missing`. */
export const planChange = (
  file: string,
  pointer: string,
  data: unknown,
  change: RuleChange,
  label: EditLabel,
): Planned => {
  const found = resolvePointer(data, pointer);
  if (!found) return { ok: false, reason: "missing" };
  const before: Guard = {
    kind: "record",
    pointer,
    exists: found.exists,
    value: found.value,
  };
  if (change.type === "set") {
    if (found.exists && sameData(found.value, change.value)) {
      return { ok: false, reason: "unchanged" };
    }
    return {
      ok: true,
      edit: {
        file,
        pointer,
        action: "set",
        ...label,
        forward: [setOp(found.path, change.value)],
        inverse: found.exists
          ? [setOp(found.path, found.value)]
          : [{ op: "delete", path: found.path }],
        before,
        after: { kind: "record", pointer, exists: true, value: change.value },
      },
    };
  }
  if (!found.exists) return { ok: false, reason: "unchanged" };
  return {
    ok: true,
    edit: {
      file,
      pointer,
      action: "remove",
      ...label,
      forward: [{ op: "delete", path: found.path }],
      inverse: [setOp(found.path, found.value)],
      before,
      after: { kind: "record", pointer, exists: false, value: undefined },
    },
  };
};

/** Удаление записи правила целиком (слот, пункт): обратная вставка по тому же индексу. */
export const planDelete = (
  file: string,
  record: RuleRecord,
  data: unknown,
  label: EditLabel,
): Planned => {
  const found = resolvePointer(data, record.pointer);
  const list = resolvePointer(data, record.list);
  if (!found?.exists || !found.inList || !list || !Array.isArray(list.value)) {
    return { ok: false, reason: "missing" };
  }
  const listPath = list.path;
  const length = list.value.length;
  return {
    ok: true,
    edit: {
      file,
      pointer: record.pointer,
      action: "delete",
      ...label,
      forward: [{ op: "delete", path: found.path }],
      inverse: [
        {
          op: "insert",
          path: listPath,
          index: record.index,
          value: found.value,
        },
      ],
      before: {
        kind: "record",
        pointer: record.pointer,
        exists: true,
        value: found.value,
      },
      after: { kind: "length", pointer: record.list, length: length - 1 },
    },
  };
};

/** Манифест сейчас в том состоянии, которого ждёт откат или повтор. */
export const guardHolds = (data: unknown, guard: Guard): boolean => {
  const found = resolvePointer(data, guard.pointer);
  if (guard.kind === "length") {
    return Array.isArray(found?.value) && found.value.length === guard.length;
  }
  if (!found) return false;
  if (found.exists !== guard.exists) return false;
  return !guard.exists || sameData(found.value, guard.value);
};
