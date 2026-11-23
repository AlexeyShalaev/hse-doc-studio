import type { TFunction } from "i18next";
import type {
  OutcomeDocument,
  OutcomeMetaField,
  OutcomeParticipant,
  OutcomePoint,
  PackOutcome,
} from "@entities/pack-studio";
import { pickLocalized } from "@shared/lib/i18n/pickLocalized";

// Чистые функции центра «Результата»: из ответа сервера выбираем, что показать и какие числа
// стоят в оглавлении, заголовке и свёрнутых частях. Условий здесь не считают: берутся флаги и
// состояния, которые сервер уже посчитал (`state`, `visible`, `applies`, `present`).

type T = TFunction<"packSpace">;

export const PART_IDS = [
  "documents",
  "data",
  "people",
  "deadlines",
  "signatures",
] as const;
export type PartId = (typeof PART_IDS)[number];

/** Документ входит в комплект. Остальные (`inactive`, `absent`) попадают в «Не вошло». */
export const isIncluded = (doc: OutcomeDocument): boolean =>
  doc.state === "active";

/** В какой части результата лежит элемент с ключом `<раздел>:<id>` (как у `sel`). */
export const partOfKey = (key: string): PartId | null => {
  const section = key.slice(0, key.indexOf(":"));
  switch (section) {
    case "documents":
      return "documents";
    case "meta":
    case "forms":
      return "data";
    case "participants":
      return "people";
    case "points":
      return "deadlines";
    case "route":
      return "signatures";
    default:
      return null;
  }
};

export const sections = {
  document: (id: string): string => `documents:${id}`,
  field: (id: string): string => `meta:${id}`,
  form: (id: string): string => `forms:${id}`,
  person: (persona: string): string => `participants:${persona}`,
  point: (id: string): string => `points:${id}`,
  item: (point: string, doc: string): string => `points:${point}/${doc}`,
  route: (point: string): string => `route:${point}`,
  skipped: (point: string, doc: string, slot: string): string =>
    `route:${point}/${doc}/${slot}`,
} as const;

/** Персоны, которых при этих условиях нет (`present: false`). */
const absentPersonas = (outcome: PackOutcome): Set<string> =>
  new Set(outcome.participants.filter((p) => !p.present).map((p) => p.persona));

/** Люди шагов подписания, которые есть в проекте: участника, которого нет, студент не увидит. */
export const routeSteps = (
  outcome: PackOutcome,
  point: OutcomePoint,
): string[][] => {
  const absent = absentPersonas(outcome);
  return point.route.steps
    .map((step) =>
      step
        .map((person) => person.persona)
        .filter((persona) => !absent.has(persona)),
    )
    .filter((step) => step.length > 0);
};

export type ResultCounts = {
  documents: number;
  /** Поля проекта, которые студент видит, плюс анкеты, которые к нему применяются. */
  data: number;
  fields: number;
  forms: number;
  needAtCreate: number;
  people: number;
  deadlines: number;
  signatures: number;
  /** Точки, где есть подписи. */
  signedPoints: number;
  signers: number;
};

export const countResult = (outcome: PackOutcome): ResultCounts => {
  const signers = new Set<string>();
  let signatures = 0;
  let signedPoints = 0;
  for (const point of outcome.points) {
    signatures += point.route.pairs.length;
    if (point.route.pairs.length > 0) signedPoints += 1;
    for (const step of routeSteps(outcome, point)) {
      for (const persona of step) signers.add(persona);
    }
  }
  const visible = outcome.meta.filter((field) => field.visible);
  const forms = outcome.forms.filter((form) => form.applies).length;
  return {
    documents: outcome.documents.filter(isIncluded).length,
    data: visible.length + forms,
    fields: visible.length,
    forms,
    needAtCreate: visible.filter((field) => field.required_at === "create")
      .length,
    people: outcome.participants.filter((p) => p.present).length,
    deadlines: outcome.points.length,
    signatures,
    signedPoints,
    signers: signers.size,
  };
};

/** Число в оглавлении слева. */
export const navCount = (counts: ResultCounts, part: PartId): number =>
  ({
    documents: counts.documents,
    data: counts.data,
    people: counts.people,
    deadlines: counts.deadlines,
    signatures: counts.signatures,
  })[part];

/** Заголовок: «Студент получит 8 документов». */
export const headline = (t: T, counts: ResultCounts): string =>
  counts.documents === 0
    ? t("result.titleNone")
    : t("result.title", { count: counts.documents });

/** Строка под заголовком: «Подписывают 2 человека, сдача в 3 точках.» */
export const leadLine = (t: T, counts: ResultCounts): string => {
  const signers =
    counts.signers === 0
      ? t("result.signersNone")
      : t("result.signers", { count: counts.signers });
  const points =
    counts.deadlines === 0
      ? t("result.pointsNone")
      : t("result.points", { count: counts.deadlines });
  return `${signers}, ${points}.`;
};

const lower = (text: string): string =>
  text.charAt(0).toLowerCase() + text.slice(1);

/** Подпись участника или персоны шага: «Автор 2», «Руководитель». */
export const personaLabel = (t: T, persona: string): string => {
  const num = /^author(\d+)$/.exec(persona)?.[1];
  if (num) return t("result.people.authorN", { n: num });
  return t(`result.people.role.${persona}`, { defaultValue: persona });
};

/** Роль участника с организацией: «руководитель из ВШЭ» для строки итога. */
const roleWithOrg = (t: T, person: OutcomeParticipant): string => {
  const role = personaLabel(t, person.persona);
  return person.org && person.role !== "author"
    ? `${lower(role)} ${t(`result.people.from.${person.org}`)}`
    : lower(role);
};

/** Итог свёрнутой части. */
export const partSummary = (
  t: T,
  lang: string,
  outcome: PackOutcome,
  counts: ResultCounts,
  part: PartId,
): string => {
  switch (part) {
    case "documents":
      return t("result.summary.documents", { count: counts.documents });
    case "data": {
      if (counts.data === 0) return t("result.summary.noData");
      const bits = [t("result.summary.fields", { count: counts.fields })];
      if (counts.needAtCreate > 0) {
        bits.push(
          t("result.summary.needAtCreate", { count: counts.needAtCreate }),
        );
      }
      if (counts.forms > 0) {
        bits.push(t("result.summary.forms", { count: counts.forms }));
      }
      return bits.join(", ");
    }
    case "people": {
      const present = outcome.participants.filter((p) => p.present);
      return present.length === 0
        ? t("result.summary.noPeople")
        : present.map((person) => roleWithOrg(t, person)).join(", ");
    }
    case "deadlines":
      return counts.deadlines === 0
        ? t("result.summary.noPoints")
        : t("result.summary.points", {
            count: counts.deadlines,
            names: outcome.points
              .map((point) =>
                shortName(pickLocalized(point.name, lang, point.id)),
              )
              .join(", "),
          });
    case "signatures":
      return counts.signatures === 0
        ? t("result.summary.noSignatures")
        : t("result.summary.signatures", {
            count: counts.signatures,
            points: t("result.summary.signaturePoints", {
              count: counts.signedPoints,
            }),
          });
  }
};

/** «КТ3 — Итоговая аттестация» -> «КТ3»: для перечислений, где полное название не влезает. */
export const shortName = (name: string): string => {
  const cut = /\s[—–-]\s/.exec(name)?.index;
  return cut === undefined ? name : name.slice(0, cut);
};

/** Порядок подписания словами: «Автор, затем руководитель и соруководитель». */
export const routeText = (
  t: T,
  outcome: PackOutcome,
  point: OutcomePoint,
): string => {
  const steps = routeSteps(outcome, point).map((step) =>
    step.map((persona, index) => {
      const label = personaLabel(t, persona);
      return index === 0 ? label : lower(label);
    }),
  );
  const joined = steps.map((step) =>
    step.reduce((first, next) =>
      t("result.signatures.and", { first, second: next }),
    ),
  );
  if (joined.length === 0) return "";
  return joined.reduce((first, next) =>
    t("result.signatures.then", { first, next: lower(next) }),
  );
};

export type FieldGroup = { id: string; fields: OutcomeMetaField[] };

/** Поля по группам в порядке первого появления группы; без группы это «Прочее» в конце. */
export const groupFields = (
  fields: readonly OutcomeMetaField[],
): FieldGroup[] => {
  const map = new Map<string, OutcomeMetaField[]>();
  for (const field of fields) {
    const key = field.group ?? "";
    const list = map.get(key);
    if (list) list.push(field);
    else map.set(key, [field]);
  }
  const groups = [...map.entries()].map(([id, list]) => ({ id, fields: list }));
  return [
    ...groups.filter((group) => group.id !== ""),
    ...groups.filter((group) => group.id === ""),
  ];
};

export type DocGroup = { id: string; docs: OutcomeDocument[] };

/** Документы по группам в порядке первого появления; без группы идут в конце. */
export const groupDocuments = (
  docs: readonly OutcomeDocument[],
): DocGroup[] => {
  const map = new Map<string, OutcomeDocument[]>();
  for (const doc of docs) {
    const key = doc.group ?? "";
    const list = map.get(key);
    if (list) list.push(doc);
    else map.set(key, [doc]);
  }
  const groups = [...map.entries()].map(([id, list]) => ({ id, docs: list }));
  return [
    ...groups.filter((group) => group.id !== ""),
    ...groups.filter((group) => group.id === ""),
  ];
};

/** Имена файлов документа без повторов; у личных документов их по одному на автора. */
export const fileNames = (doc: OutcomeDocument): string[] => [
  ...new Set(
    doc.instances
      .map((instance) => instance.file_name)
      .filter((name): name is string => name !== null && name !== ""),
  ),
];

/** Совпадает ли что-то из `fields` с поиском: без регистра, по подстроке. */
export const matchesQuery = (
  query: string,
  ...fields: (string | null)[]
): boolean => {
  const q = query.trim().toLowerCase();
  return (
    q === "" ||
    fields.some((field) => field?.toLowerCase().includes(q) === true)
  );
};

/** Больше стольких документов: появляются поиск и фильтр (раздел 9.3, срез S6). */
export const FILTER_THRESHOLD = 10;
