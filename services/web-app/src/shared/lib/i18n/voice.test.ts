import { readdirSync, readFileSync, statSync } from "node:fs";
import { join, relative } from "node:path";
import { describe, expect, it } from "vitest";

// Интерфейс обращается к человеку на «вы». Ловим частые формы на «ты» в
// русских словарях: местоимения, глаголы 2-го лица и повелительные формы.
// Ключи *prompt* - это текст, который человек отправляет ИИ-агенту от своего
// имени («исправь…»), к ним правило не относится.

const RU = join(import.meta.dirname, "locales", "ru");

const PRONOUNS = [
  "ты",
  "тебе",
  "тебя",
  "тобой",
  "твой",
  "твоя",
  "твоё",
  "твое",
  "твои",
  "твоих",
  "твоего",
  "твоей",
  "твоим",
  "твою",
];

const IMPERATIVES = [
  "добавь",
  "проверь",
  "открой",
  "нажми",
  "выбери",
  "введи",
  "укажи",
  "попробуй",
  "сохрани",
  "загрузи",
  "удали",
  "перейди",
  "обнови",
  "подожди",
  "создай",
  "задай",
  "напиши",
  "скопируй",
  "вставь",
  "войди",
  "посмотри",
  "убедись",
  "исправь",
  "перезапусти",
  "свяжись",
  "включи",
  "выключи",
  "отключи",
  "подключи",
  "запусти",
  "заполни",
  "поправь",
  "отправь",
  "повтори",
  "попроси",
  "выпусти",
  "установи",
  "используй",
  "вернись",
  "обратись",
  "перетащи",
  "представься",
  "синхронизируй",
  "подтверди",
  "сбрось",
  "скачай",
  "дождись",
];

const WORD = new RegExp(
  `(?<![а-яё])(${[...PRONOUNS, ...IMPERATIVES].join("|")})(?![а-яё])`,
  "i",
);
// Глагол 2-го лица единственного числа: «сможешь», «обновишь», «скачаешь».
const SECOND_PERSON = /(?<![а-яё])[а-яё]{2,}(ешь|ёшь|ишь)(?![а-яё])/i;

const jsonFiles = (dir: string): string[] =>
  readdirSync(dir).flatMap((name) => {
    const path = join(dir, name);
    if (statSync(path).isDirectory()) return jsonFiles(path);
    return name.endsWith(".json") ? [path] : [];
  });

const strings = (
  value: unknown,
  key = "",
): Array<{ key: string; text: string }> => {
  if (typeof value === "string") return [{ key, text: value }];
  if (value !== null && typeof value === "object") {
    return Object.entries(value as Record<string, unknown>).flatMap(
      ([k, child]) => strings(child, key ? `${key}.${k}` : k),
    );
  }
  return [];
};

describe("ru locales speak «вы»", () => {
  it("has no «ты» forms in user-facing strings", () => {
    const offenders = jsonFiles(RU).flatMap((file) =>
      strings(JSON.parse(readFileSync(file, "utf8")))
        .filter(({ key }) => !/prompt/i.test(key))
        .filter(({ text }) => WORD.test(text) || SECOND_PERSON.test(text))
        .map(({ key, text }) => `${relative(RU, file)} ${key}: ${text}`),
    );
    expect(offenders).toEqual([]);
  });
});
