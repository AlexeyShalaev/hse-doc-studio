import type { PackOutcome } from "@entities/pack-studio";
import { pickLocalized } from "@shared/lib/i18n/pickLocalized";
import { absentPersonas } from "./routeSteps";

// Вид «Как студент» (template-studio-outcome.md, срез F13): те же данные ответа сервера, но
// только то, что увидит студент проекта. Ничего не вычисляется: берутся состояния и флаги,
// которые сервер уже посчитал (`active`, `visible`, `applies`, `present`), и убираются служебные
// метки (причины, источники, идентификаторы, пропущенное условием, `may_add`).

export type StudentDocument = {
  id: string;
  name: string;
  group: string;
  required: boolean;
  /** Итоговые имена файлов; у личных документов с автором. */
  files: { owner: string | null; name: string }[];
};

/** Документы комплекта: только `active`. Группа `""` у документов без группы. */
export const studentDocuments = (
  outcome: PackOutcome,
  lang: string,
): StudentDocument[] =>
  outcome.documents
    .filter((doc) => doc.state === "active")
    .map((doc) => ({
      id: doc.id,
      name: pickLocalized(doc.name, lang, doc.id),
      group: doc.group ?? "",
      required: doc.required,
      files: doc.instances
        .filter((inst) => inst.file_name !== null && inst.file_name !== "")
        .map((inst) => ({
          owner: inst.owner_name !== "" ? inst.owner_name : null,
          name: inst.file_name ?? "",
        })),
    }));

export type StudentField = {
  id: string;
  label: string;
  /** Заполняет каждый автор (поле автора). */
  perAuthor: boolean;
};

export type StudentMeta = {
  create: StudentField[];
  finalize: StudentField[];
};

/** Обязательные поля проекта, видимые студенту, по моменту (при создании, при финализации). Скрытые и необязательные не показываются. */
export const studentMeta = (
  outcome: PackOutcome,
  lang: string,
): StudentMeta => {
  const out: StudentMeta = { create: [], finalize: [] };
  for (const field of outcome.meta) {
    if (!field.visible) continue;
    const item: StudentField = {
      id: field.id,
      label: pickLocalized(field.label, lang, field.id),
      perAuthor: field.scope === "author",
    };
    if (field.required_at === "create") out.create.push(item);
    else if (field.required_at === "finalize") out.finalize.push(item);
  }
  return out;
};

export type StudentForm = {
  id: string;
  title: string;
  perAuthor: boolean;
  required: boolean;
  fields: { id: string; label: string; required: boolean }[];
};

/** Анкеты, которые применяются при комбинации, и их видимые поля. */
export const studentForms = (
  outcome: PackOutcome,
  lang: string,
): StudentForm[] =>
  outcome.forms
    .filter((form) => form.applies)
    .map((form) => ({
      id: form.id,
      title: pickLocalized(form.title, lang, form.id),
      perAuthor: form.per_author,
      required: form.required_for_pack,
      fields: form.fields
        .filter((field) => field.visible)
        .map((field) => ({
          id: field.id,
          label: pickLocalized(field.label, lang, field.id),
          required: field.required,
        })),
    }));

export type StudentSigner = {
  persona: string;
  name: string;
  /** Документы, которые этот человек подписывает в точке. */
  documents: { id: string; name: string; optional: boolean }[];
};

export type StudentPoint = {
  id: string;
  name: string;
  deadline: string;
  /** Шаги по порядку: внутри шага подписывают параллельно. */
  steps: StudentSigner[][];
};

/**
 * Порядок подписания по точкам: только шаги с людьми, которые есть в проекте (участника, которого
 * нет при этой комбинации, студент не увидит). Пустые шаги пропускаются, номера идут подряд.
 */
export const studentRoute = (
  outcome: PackOutcome,
  lang: string,
): StudentPoint[] => {
  const absent = absentPersonas(outcome);
  const docName = new Map(
    outcome.documents.map((d) => [d.id, pickLocalized(d.name, lang, d.id)]),
  );
  const out: StudentPoint[] = [];
  for (const point of outcome.points) {
    const steps: StudentSigner[][] = [];
    for (const step of point.route.steps) {
      const people = step
        .filter((person) => !absent.has(person.persona))
        .map((person) => ({
          persona: person.persona,
          name: person.name.trim(),
          documents: point.route.pairs
            .filter((pair) => pair.persona === person.persona)
            .map((pair) => ({
              id: `${pair.doc_id}/${pair.slot_id}`,
              name: docName.get(pair.doc_id) ?? pair.doc_id,
              optional: pair.optional,
            })),
        }));
      if (people.length > 0) steps.push(people);
    }
    if (steps.length === 0) continue;
    out.push({
      id: point.id,
      name: pickLocalized(point.name, lang, point.id),
      deadline: point.deadline_hint
        ? pickLocalized(point.deadline_hint, lang, "")
        : "",
      steps,
    });
  }
  return out;
};
