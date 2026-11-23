import type { TFunction } from "i18next";
import type { OutcomeInput } from "@entities/pack-studio";
import { pickLocalized } from "@shared/lib/i18n/pickLocalized";
import { STANDARD_INPUTS, isToken } from "@entities/pack-studio/outcome/inputs";

// Слова условий для «Почему так»: как называется условие студента и его значение. Подписи берутся
// у самих условий версии (ответ `inputs`), затем те же слова, что на полосе «Для какого студента»
// (`situation.std`, `situation.values`): условие в объяснении называется так же, как кнопка, которой
// его меняют. Чего нет и там, из запасного словаря области.

export type Words = {
  /** Название условия: `kind` -> «Вид работы». */
  subject: (id: string) => string;
  /** Значение условия: `project` -> «Проектная». */
  value: (subject: string, raw: string) => string;
};

/** Слово в середину фразы: первая буква строчная, если это не сокращение вроде «ВШЭ» или «NDA». */
export const soft = (text: string): string => {
  const [first = "", second = ""] = text;
  if (first === "" || first === first.toLowerCase()) return text;
  if (
    second !== "" &&
    second === second.toUpperCase() &&
    /\p{L}/u.test(second)
  ) {
    return text;
  }
  return first.toLowerCase() + text.slice(1);
};

/** Слово в начало фразы: первая буква заглавная. */
export const sentence = (text: string): string =>
  text === "" ? text : text.charAt(0).toUpperCase() + text.slice(1);

export const makeWords = (
  t: TFunction,
  lang: string,
  inputs: readonly OutcomeInput[] | undefined,
): Words => {
  const input = (id: string) => inputs?.find((item) => item.id === id);
  const lookup = (group: "subject" | "value", key: string): string | null =>
    t(`details.dict.${group}.${key}`, { defaultValue: "" }) || null;
  const strip = (key: string): string | null =>
    t(`situation.${key}`, { defaultValue: "" }) || null;

  const subject = (id: string): string => {
    // `supervisor.role`: организация человека, подпись строится от подписи самого человека.
    const person = /^(.+)\.role$/.exec(id)?.[1];
    if (person && !input(id)) {
      return t("details.dict.orgOf", { subject: soft(subject(person)) });
    }
    const label = input(id)?.label;
    if (label) return pickLocalized(label, lang, id);
    const std = STANDARD_INPUTS.includes(id) ? strip(`std.${id}`) : null;
    return std ?? lookup("subject", id) ?? id;
  };
  const value = (id: string, raw: string): string => {
    const label = input(id)?.values.find((item) => item.value === raw)?.label;
    if (label) return pickLocalized(label, lang, raw);
    // Языки в объяснении называются по-русски («Русский, Английский»), как в списке редакций.
    const own =
      id !== "lang" && STANDARD_INPUTS.includes(id) && isToken(raw)
        ? strip(`values.${id}.${raw}`)
        : null;
    return own ?? lookup("value", raw) ?? raw;
  };
  return { subject, value };
};
