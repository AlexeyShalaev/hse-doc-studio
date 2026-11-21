import { readdirSync, readFileSync } from "node:fs";
import { join } from "node:path";
import { describe, expect, it } from "vitest";
import banned from "./vocabulary.banned.json";

// Словарь нового интерфейса (docs/design/pack-studio-ux.md, раздел 6): в строках packSpace нет
// слов из списка «жаргон». Список лежит в vocabulary.banned.json и растёт вместе со словарём.

type Rule = { id: string; pattern: string; use: string };
const LOCALES = join(import.meta.dirname, "../../shared/lib/i18n/locales");
const LANGS = ["ru", "en"] as const;

const areasOf = (lng: string): string[] =>
  readdirSync(join(LOCALES, lng, "packSpace"))
    .filter((file) => file.endsWith(".json"))
    .map((file) => file.replace(/\.json$/, ""))
    .sort();

const read = (lng: string, area: string): unknown =>
  JSON.parse(
    readFileSync(join(LOCALES, lng, "packSpace", `${area}.json`), "utf8"),
  );

const leaves = (value: unknown, prefix = ""): [string, string][] =>
  value !== null && typeof value === "object"
    ? Object.entries(value).flatMap(([key, child]) =>
        leaves(child, prefix ? `${prefix}.${key}` : key),
      )
    : [[prefix, String(value)]];

const allowed = (area: string): Set<string> =>
  new Set((banned.allowedIn as Record<string, string[]>)[area] ?? []);

describe("словарь packSpace", () => {
  it("ru и en: те же области и те же ключи", () => {
    expect(areasOf("en")).toEqual(areasOf("ru"));
    for (const area of areasOf("ru")) {
      expect(
        leaves(read("en", area)).map(([key]) => key),
        area,
      ).toEqual(leaves(read("ru", area)).map(([key]) => key));
    }
  });

  it("у каждой области есть файл (shell, list, situation, result, details, content, changes, check, admin)", () => {
    expect(areasOf("ru")).toEqual(
      [
        "admin",
        "changes",
        "check",
        "content",
        "details",
        "list",
        "result",
        "shell",
        "situation",
      ].sort(),
    );
  });

  it.each(LANGS)("(%s) нет запрещённых слов", (lng) => {
    const rules = banned[lng] as Rule[];
    const hits: string[] = [];
    for (const area of areasOf(lng)) {
      const skip = allowed(area);
      for (const [key, text] of leaves(read(lng, area))) {
        for (const rule of rules) {
          if (skip.has(rule.id)) continue;
          if (new RegExp(rule.pattern, "iu").test(text)) {
            hits.push(
              `${area}.${key}: «${text}» (${rule.id}; вместо этого: ${rule.use})`,
            );
          }
        }
      }
    }
    expect(hits).toEqual([]);
  });

  it("правила рабочие: ловят слова из раздела 6", () => {
    const hit = (lng: "ru" | "en", text: string): string[] =>
      (banned[lng] as Rule[])
        .filter((rule) => new RegExp(rule.pattern, "iu").test(text))
        .map((rule) => rule.id);
    expect(hit("ru", "Вводные")).toContain("inputs");
    expect(hit("ru", "Сохранить как сценарий")).toContain("scenario");
    expect(hit("ru", "Матрица и Атлас")).toEqual(
      expect.arrayContaining(["matrix", "atlas"]),
    );
    expect(hit("ru", "Предложить изменения")).toContain("propose");
    expect(hit("ru", "Подтянуть main")).toContain("pull-base");
    expect(hit("ru", "База")).toContain("base");
    expect(hit("ru", "Базовая настройка")).not.toContain("base");
    expect(hit("ru", "Открыть PR")).toContain("pr");
    expect(hit("ru", "Проверка шаблона: 0 ошибок")).toEqual([]);
    expect(hit("en", "Open the PR")).toContain("pr");
    expect(hit("en", "Atlas of inputs")).toEqual(
      expect.arrayContaining(["atlas", "inputs"]),
    );
  });

  it("идентификаторы правил уникальны, а allowedIn ссылается на существующие", () => {
    for (const lng of LANGS) {
      const ids = (banned[lng] as Rule[]).map((rule) => rule.id);
      expect(new Set(ids).size).toBe(ids.length);
    }
    const known = new Set(
      LANGS.flatMap((lng) => (banned[lng] as Rule[]).map((rule) => rule.id)),
    );
    for (const ids of Object.values(banned.allowedIn)) {
      for (const id of ids) expect(known.has(id)).toBe(true);
    }
  });
});
