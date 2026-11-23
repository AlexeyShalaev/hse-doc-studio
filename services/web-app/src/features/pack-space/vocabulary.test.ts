import { readdirSync, readFileSync } from "node:fs";
import { join } from "node:path";
import { beforeAll, describe, expect, it } from "vitest";
import type { TFunction } from "i18next";
import { i18n } from "@shared/lib";
import { loadPackSpaceNamespace } from "@shared/lib/i18n/packSpaceNamespace";
import { plainTexts } from "./plain/textsKit";
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
    // Формы числа (`_one`, `_few`...) у языков разные: сравниваем ключи без них.
    const keys = (lng: string, area: string): string[] => [
      ...new Set(
        leaves(read(lng, area)).map(([key]) =>
          key.replace(/_(zero|one|two|few|many|other)$/, ""),
        ),
      ),
    ];
    for (const area of areasOf("ru")) {
      expect(keys("en", area), area).toEqual(keys("ru", area));
    }
  });

  it("у каждой области есть файл (shell, nav, list, situation, result, details, content, changes, check, admin)", () => {
    // Области добавляют срезы (nav, preview, ...), поэтому проверяем наличие, а не точный список.
    expect(areasOf("ru")).toEqual(
      expect.arrayContaining([
        "admin",
        "changes",
        "check",
        "content",
        "details",
        "list",
        "nav",
        "result",
        "shell",
        "situation",
      ]),
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
    expect(hit("ru", "Рабочее пространство")).toContain("workspace");
    expect(hit("ru", "Служебный доступ")).toContain("service-access");
    expect(hit("ru", "Нужно право «Автор шаблонов»")).toContain("author-right");
    expect(hit("ru", "Результат из: рабочее дерево")).toContain("result-from");
    expect(hit("ru", "Результат изменился")).not.toContain("result-from");
    expect(hit("ru", "Пересчитываю")).toContain("recalculating");
    expect(hit("ru", "Папка паков")).toContain("packs-folder");
    expect(hit("en", "Template author right")).toContain("author-right");
    expect(hit("en", "Coverage by scenarios")).toEqual(
      expect.arrayContaining(["coverage", "scenario"]),
    );
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

// Формы «Содержимого» (pack-studio-ux.md, 5.5 и раздел 6): строки форм живут в общих словарях
// packForms и packStudio (ими пользуется и прежний интерфейс), поэтому проверяются только их ключи,
// перечисленные в `forms.scopes`. Ключи под `tech` (технические подробности) не проверяются:
// идентификаторы и имена файлов допустимы там и только там.

type FormScope = { file: string; prefixes: string[] };
const formsVocabulary = banned.forms as {
  ru: Rule[];
  en: Rule[];
  scopes: FormScope[];
};
const IS_TECH = /(^|\.)tech(\.|$)/;
const readLocale = (lng: string, file: string): unknown =>
  JSON.parse(readFileSync(join(LOCALES, lng, file), "utf8"));
/** Без подстановок `{{id}}`: имя переменной не видно человеку. */
const visible = (text: string): string => text.replace(/\{\{[^}]*\}\}/g, "");

// Экраны Студии шаблонов вне packSpace (список пространств, окно официальных шаблонов и подсказка
// по токену): те же правила «жаргон», но только для ключей из `surfaces.scopes`.
const surfaces = banned.surfaces as { scopes: FormScope[] };

describe("словарь списка пространств и окна официальных шаблонов", () => {
  it.each(LANGS)("(%s) нет запрещённых слов", (lng) => {
    const rules = banned[lng] as Rule[];
    const hits: string[] = [];
    let checked = 0;
    for (const scope of surfaces.scopes) {
      for (const [key, text] of leaves(readLocale(lng, scope.file))) {
        if (IS_TECH.test(key)) continue;
        if (!scope.prefixes.some((p) => key === p || key.startsWith(`${p}.`))) {
          continue;
        }
        checked += 1;
        for (const rule of rules) {
          if (new RegExp(rule.pattern, "iu").test(visible(text))) {
            hits.push(
              `${scope.file}: ${key}: «${text}» (${rule.id}; вместо этого: ${rule.use})`,
            );
          }
        }
      }
    }
    expect(checked).toBeGreaterThan(20);
    expect(hits).toEqual([]);
  });
});

describe("словарь форм «Содержимого»", () => {
  it("ru и en: те же ключи в проверяемых областях", () => {
    for (const scope of formsVocabulary.scopes) {
      // Формы числа (`_one`, `_few`...) у языков разные: сравниваем ключи без них.
      const keys = (lng: string) => [
        ...new Set(
          leaves(readLocale(lng, scope.file)).map(([key]) =>
            key.replace(/_(zero|one|two|few|many|other)$/, ""),
          ),
        ),
      ];
      expect(keys("en"), scope.file).toEqual(keys("ru"));
    }
  });

  it.each(LANGS)(
    "(%s) нет идентификаторов, имён файлов и внутренних слов",
    (lng) => {
      const rules = formsVocabulary[lng];
      const hits: string[] = [];
      for (const scope of formsVocabulary.scopes) {
        for (const [key, text] of leaves(readLocale(lng, scope.file))) {
          if (IS_TECH.test(key)) continue;
          if (
            !scope.prefixes.some((p) => p === "" || key.startsWith(`${p}.`))
          ) {
            continue;
          }
          for (const rule of rules) {
            if (new RegExp(rule.pattern, "iu").test(visible(text))) {
              hits.push(
                `${scope.file}: ${key}: «${text}» (${rule.id}; вместо этого: ${rule.use})`,
              );
            }
          }
        }
      }
      expect(hits).toEqual([]);
    },
  );

  it("правила рабочие: ловят слова из жалоб проверяющего", () => {
    const hit = (text: string): string[] =>
      formsVocabulary.ru
        .filter((rule) => new RegExp(rule.pattern, "iu").test(visible(text)))
        .map((rule) => rule.id);
    expect(hit("Документ technical_specification")).toContain("snake-case");
    expect(hit("Описание документа (doc.yaml)")).toContain("yaml");
    expect(hit("Группа навигации ЕСПД")).toContain("navigation-group");
    expect(hit("Незнакомая Студии группа показывается как «Прочее»")).toContain(
      "unknown-to-studio",
    );
    expect(hit("Идентификатор checkpoint-1")).toEqual(
      expect.arrayContaining(["identifier", "checkpoint"]),
    );
    expect(hit("Id пака")).toContain("id-word");
    expect(hit("Идентификатор SPDX")).toEqual(
      expect.arrayContaining(["identifier", "spdx"]),
    );
    expect(hit("версия beta, реестр выпусков, манифест")).toEqual(
      expect.arrayContaining(["beta", "release-registry", "manifest"]),
    );
    expect(hit("Языки задают суффиксы файлов")).toContain("suffix");
    expect(hit("Название {{id}} по-русски")).toEqual([]);
    expect(hit("Короткое имя документа")).toEqual([]);
  });

  it("технические подробности вынесены под tech: сам блок существует", () => {
    const ru = readLocale("ru", "packForms/packForms.json") as {
      doc: { tech: Record<string, string> };
    };
    expect(Object.keys(ru.doc.tech)).toEqual(
      expect.arrayContaining(["sourceFile", "outputFile"]),
    );
  });
});

// Сообщения сервера (находки линтера результата, сбои сборки PDF, изменения «Сравнить») приходят
// не из словаря, а из кода сервера на русском и с внутренними словами. Они проходят слой
// формулировок (`plain/`); тест прогоняет формулировщик по фикстурам всех 22 правил, кодов
// ошибок сборки и видов изменений и ищет в видимом тексте те же запрещённые слова, что у словаря,
// и утечки идентификаторов (список `server`). Технические подробности не проверяются.

const serverRules = banned.server as { ru: Rule[]; en: Rule[] };

describe("серверные сообщения через слой формулировок", () => {
  beforeAll(async () => {
    await loadPackSpaceNamespace();
  });

  it.each(LANGS)(
    "(%s) нет запрещённых слов и утечек идентификаторов",
    async (lng) => {
      await i18n.changeLanguage(lng);
      const t: TFunction = i18n.getFixedT(lng, "packSpace");
      const rules = [...(banned[lng] as Rule[]), ...serverRules[lng]];
      const hits: string[] = [];
      for (const named of [true, false]) {
        for (const { key, text } of plainTexts(t, lng, named)) {
          for (const rule of rules) {
            if (new RegExp(rule.pattern, "iu").test(text)) {
              hits.push(
                `${named ? "с названиями" : "без названий"} ${key}: «${text}» (${rule.id}; вместо этого: ${rule.use})`,
              );
            }
          }
        }
      }
      expect([...new Set(hits)]).toEqual([]);
    },
  );
});
