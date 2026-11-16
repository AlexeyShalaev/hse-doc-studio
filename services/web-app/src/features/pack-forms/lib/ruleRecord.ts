import { asArray, asRecord, asString, asStrings } from "./raw";
import { KINDS } from "./fields";
import { STAFFING, versionLangs } from "./documents";

// Одна запись манифеста в мини-форме (правка по месту с экрана «Результат»): что за правило,
// какие значения у него бывают и как они читаются из манифеста. Условий пака здесь нет: форма
// лишь показывает и пишет значение записи, а что оно решает, считает сервер.

/** Вид записи: по нему выбирается поле формы. */
export type RuleShape =
  | { kind: "list"; list: "kinds" | "staffing" | "langs" }
  | { kind: "flag"; flag: "skip_if_nda" | "optional" }
  | { kind: "visibleIf" }
  | { kind: "when" }
  | { kind: "checks"; list: "disabled" | "categories" }
  | { kind: "route" };

/** Что форма берёт из модели версии для списков выбора. */
export type RuleFormContext = {
  /** Данные `version.yaml` как их отдаёт модель. */
  manifest: unknown;
  /** Правила проверок версии. */
  checkRules: readonly string[];
  /** Категории правил проверок, которые известны экрану. */
  checkCategories: readonly string[];
};

/** Что форма хочет записать: новое значение записи или убрать ключ (значение по умолчанию). */
export type RuleChange = { type: "set"; value: unknown } | { type: "remove" };

export const WHEN_PERSONS = [
  "supervisor",
  "co_supervisor",
  "academic_supervisor",
] as const;
export const WHEN_ROLES = ["university", "company"] as const;

/** Закрытый список условий слота: «всегда» и человек с ролью или без. */
export const WHEN_CHOICES: readonly string[] = [
  "always",
  ...WHEN_PERSONS.flatMap((person) => [
    person,
    ...WHEN_ROLES.map((role) => `${person}:${role}`),
  ]),
];

export const whenChoice = (value: unknown): string => {
  const when = asRecord(value);
  const person = asString(when.person);
  if (!person) return "always";
  const role = asString(when.role);
  return role ? `${person}:${role}` : person;
};

/** Значение условия слота по выбору; «всегда» это отсутствие ключа. */
export const whenValue = (choice: string): RuleChange => {
  if (choice === "always") return { type: "remove" };
  const [person = "", role] = choice.split(":");
  return {
    type: "set",
    value: role ? { person, role } : { person },
  };
};

/** Поля анкеты, на которые может ссылаться `visible_if` записи по указателю (кроме неё самой). */
export const siblingFields = (manifest: unknown, pointer: string): string[] => {
  const match = /^\/forms\/(\d+)\/sections\/\d+\/fields\/(\d+)\//.exec(pointer);
  if (!match) return [];
  const form = asRecord(asArray(asRecord(manifest).forms)[Number(match[1])]);
  const self = pointer.replace(/\/visible_if$/, "");
  const out: string[] = [];
  asArray(form.sections).forEach((section, s) => {
    asArray(asRecord(section).fields).forEach((field, f) => {
      const id = asString(asRecord(field).id);
      const at = `/forms/${match[1] ?? ""}/sections/${String(s)}/fields/${String(f)}`;
      if (id && at !== self) out.push(id);
    });
  });
  return out;
};

/** Варианты списка: все значения, которыми правило может быть ограничено. */
export const listOptions = (
  list: "kinds" | "staffing" | "langs",
  manifest: unknown,
): string[] =>
  list === "kinds"
    ? KINDS
    : list === "staffing"
      ? STAFFING
      : versionLangs(manifest);

/** Выбранные значения: пустой список или нет ключа это «без ограничения», то есть всё. */
export const selectedOf = (
  value: unknown,
  all: readonly string[],
): string[] => {
  const picked = asStrings(value);
  return picked.length > 0 ? picked : [...all];
};
