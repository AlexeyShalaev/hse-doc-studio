import { readdirSync, readFileSync } from "node:fs";
import { join } from "node:path";
import { describe, expect, it } from "vitest";

// ru и en обязаны совпадать по набору ключей: иначе на втором языке покажется
// сам ключ. Множественные формы у языков разные (ru: one/few/many/other, en:
// one/other), поэтому окончания _one/_few/... сворачиваем в базовый ключ.

const LOCALES = join(import.meta.dirname, "locales");
const PLURAL = /_(zero|one|two|few|many|other)$/;

const leafKeys = (value: unknown, prefix = ""): string[] => {
  if (value !== null && typeof value === "object") {
    return Object.entries(value as Record<string, unknown>).flatMap(
      ([key, child]) => leafKeys(child, prefix ? `${prefix}.${key}` : key),
    );
  }
  return [prefix.replace(PLURAL, "")];
};

const keysOf = (lang: string, file: string): string[] =>
  [
    ...new Set(
      leafKeys(JSON.parse(readFileSync(join(LOCALES, lang, file), "utf8"))),
    ),
  ].sort();

const NEW_NAMESPACES = [
  "gitSync",
  "gitRemote",
  "gitAccess",
  "gitExchange",
  "gitConflicts",
  "profile",
];

describe("locale parity", () => {
  const namespaces = readdirSync(join(LOCALES, "ru"))
    .filter((f) => f.endsWith(".json"))
    .sort();

  it("ships the same files in both languages", () => {
    expect(
      readdirSync(join(LOCALES, "en"))
        .filter((f) => f.endsWith(".json"))
        .sort(),
    ).toEqual(namespaces);
  });

  it.each(namespaces)("%s has the same keys in ru and en", (file) => {
    expect(keysOf("en", file)).toEqual(keysOf("ru", file));
  });

  it.each(NEW_NAMESPACES)("%s exists and is not empty", (ns) => {
    expect(namespaces).toContain(`${ns}.json`);
    expect(keysOf("ru", `${ns}.json`).length).toBeGreaterThan(5);
  });
});

// Словари админки лежат в подкаталоге admin/ и грузятся лениво; паритет тот же.
describe("admin locale parity", () => {
  const adminFiles = (lang: string) =>
    readdirSync(join(LOCALES, lang, "admin")).sort();

  it("ships the same admin files in both languages", () => {
    expect(adminFiles("en")).toEqual(adminFiles("ru"));
    expect(adminFiles("ru").length).toBeGreaterThan(0);
  });

  it.each(adminFiles("ru"))("admin/%s has the same keys in ru and en", (f) => {
    expect(keysOf("en", `admin/${f}`)).toEqual(keysOf("ru", `admin/${f}`));
  });
});
