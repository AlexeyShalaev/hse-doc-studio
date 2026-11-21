import type { TFunction } from "i18next";
import type { OutcomeInput } from "@entities/pack-studio";
import { pickLocalized } from "@shared/lib/i18n/pickLocalized";

// Слова условий для «Почему так»: как называется условие студента и его значение. Подписи берутся
// у самих условий версии (ответ `inputs`), а то, чего там нет, из запасного словаря области.

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

  const subject = (id: string): string => {
    // `supervisor.role`: организация человека, подпись строится от подписи самого человека.
    const person = /^(.+)\.role$/.exec(id)?.[1];
    if (person && !input(id)) {
      return t("details.dict.orgOf", { subject: soft(subject(person)) });
    }
    const label = input(id)?.label;
    if (label) return pickLocalized(label, lang, id);
    return lookup("subject", id) ?? id;
  };
  const value = (id: string, raw: string): string => {
    const label = input(id)?.values.find((item) => item.value === raw)?.label;
    if (label) return pickLocalized(label, lang, raw);
    return lookup("value", raw) ?? raw;
  };
  return { subject, value };
};
