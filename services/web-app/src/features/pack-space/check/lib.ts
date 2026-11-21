import type { OutcomeInput, OutcomeSection } from "@entities/pack-studio";

// Чистые помощники области «Проверка»: какая часть открыта, как условия из находки ложатся на
// условия экрана, как читаются закрепления «Что на что влияет». Данные считает сервер, здесь только
// раскладка по адресу.

export const CHECK_PARTS = ["issues", "cases", "map"] as const;
export type CheckPart = (typeof CHECK_PARTS)[number];

const isPart = (value: string | null): value is CheckPart =>
  CHECK_PARTS.some((part) => part === value);

/** Открытая часть и экран сравнения из query (`part`, `compare=1`); чужое значение даёт «Замечания». */
export const readCheck = (
  search: string,
): { part: CheckPart; compare: boolean } => {
  const params = new URLSearchParams(search);
  const part = params.get("part");
  return {
    part: isPart(part) ? part : "issues",
    compare: params.get("compare") === "1",
  };
};

const PIN_PREFIX = "p.";

/** Параметр query, в котором лежит закрепление условия (`p.<условие>`). */
export const pinParam = (input: string): string => `${PIN_PREFIX}${input}`;

/**
 * Условия экрана после «Показать такую ситуацию»: значения из находки или правила ложатся поверх
 * нынешних, остальное не трогается. Условие, которого нет у версии, не пишется (сервер отклонил бы
 * весь запрос); значение по умолчанию без готового случая отдельно не пишется.
 */
export const witnessInputs = (
  known: readonly Pick<OutcomeInput, "id" | "default">[] | undefined,
  current: Readonly<Record<string, string>>,
  caseId: string | null,
  witness: Readonly<Record<string, string>>,
): Record<string, string> => {
  const defaults = known ? new Map(known.map((i) => [i.id, i.default])) : null;
  const next = new Map(Object.entries(current));
  for (const [input, value] of Object.entries(witness)) {
    if (defaults && !defaults.has(input)) continue;
    if (caseId === null && defaults?.get(input) === value) next.delete(input);
    else next.set(input, value);
  }
  return Object.fromEntries(next);
};

/** Путь файла от папки паков или `null`, если файл вне каталога версии (`..`, абсолютный путь). */
export const filePathIn = (versionPath: string, file: string): string | null =>
  versionPath === "" ||
  file === "" ||
  file.startsWith("/") ||
  file.split("/").includes("..")
    ? null
    : `${versionPath}/${file}`;

/** Подписи разделов результата для «Меняет: ...»; ключ в словаре `check.sections`. */
export const SECTION_KEYS: readonly OutcomeSection[] = [
  "documents",
  "meta",
  "forms",
  "participants",
  "points",
  "route",
  "checks",
];
