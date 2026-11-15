import type { PackFieldUsage, PackVersionModel } from "@entities/pack-studio";
import { asArray, asRecord, pickLocalized, type Raw } from "./raw";

// Поля анкеты версии (`meta_fields`) и группы (`meta_groups`): template-studio.md, 5.2.

export const FIELD_TYPES = ["string", "bool", "select", "person", "font"];
export const REQUIRED_AT = ["create", "finalize", "never"];
export const FIELD_SCOPES = ["project", "author"];
export const KINDS = ["research", "project"];
export const GROUP_SECTIONS = ["meta", "documents"];
/** Люди проекта: хранятся в собственных полях проекта, ключ не переименовать. */
export const PERSON_KEYS = [
  "supervisor",
  "co_supervisor",
  "academic_supervisor",
];

export type FieldEntry = { key: string; spec: Raw };
export type GroupEntry = { id: string; raw: Raw; index: number };

export const fieldsOf = (manifest: unknown): FieldEntry[] =>
  Object.entries(asRecord(asRecord(manifest).meta_fields)).map(
    ([key, spec]) => ({ key, spec: asRecord(spec) }),
  );

export const groupsOf = (manifest: unknown): GroupEntry[] =>
  asArray(asRecord(manifest).meta_groups).flatMap((raw, index) => {
    const record = asRecord(raw);
    const id = typeof record.id === "string" ? record.id : "";
    return id ? [{ id, raw: record, index }] : [];
  });

/** Документы, где печатается поле, в порядке ростера. */
export const usageOf = (
  model: PackVersionModel,
  key: string,
): PackFieldUsage[] => {
  const order = new Map(model.documents.map((d, i) => [d.id, i]));
  return model.usage
    .filter((u) => u.field === key)
    .sort(
      (a, b) => (order.get(a.document) ?? 0) - (order.get(b.document) ?? 0),
    );
};

/** Название документа на языке интерфейса (id, если названия нет). */
export const documentName = (
  model: PackVersionModel,
  docId: string,
  lang: string,
): string => {
  const doc = model.documents.find((d) => d.id === docId);
  return pickLocalized(asRecord(doc?.data).name, lang, docId);
};

/** Новый ключ поля годится: латиница, цифры и `_`, не занят. */
export const fieldKeyProblem = (
  key: string,
  taken: string[],
): "format" | "taken" | null => {
  if (!/^[A-Za-z_][A-Za-z0-9_]*$/.test(key) || key.length > 64) return "format";
  return taken.includes(key) ? "taken" : null;
};
