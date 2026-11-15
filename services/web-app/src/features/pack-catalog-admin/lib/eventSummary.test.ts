import { readFileSync } from "node:fs";
import { join } from "node:path";
import { beforeAll, describe, expect, it } from "vitest";
import { CatalogEventListSchema } from "@entities/pack-catalog";
import { i18n, loadAdminNamespaces } from "@shared/lib";
import { eventSummary } from "./eventSummary";

const HISTORY = CatalogEventListSchema.parse(
  JSON.parse(
    readFileSync(
      join(
        import.meta.dirname,
        "../../../../../../contracts/pack-catalog/fixtures/CatalogEventList/history.json",
      ),
      "utf8",
    ),
  ),
);
const event = (index: number) => {
  const found = HISTORY[index];
  if (!found) throw new Error(`нет события ${String(index)}`);
  return found;
};

describe("сводка события истории", () => {
  beforeAll(async () => {
    await loadAdminNamespaces(["packCatalog"]);
    await i18n.changeLanguage("ru");
  });

  it("применение: добавленные версии, без служебного номера каталога", () => {
    expect(eventSummary(event(0))).toEqual([
      "добавлена 1 версия: acme-thesis/thesis@2026.1.0",
    ]);
  });

  it("проверка: новые версии и паки", () => {
    expect(eventSummary(event(1))).toEqual([
      "2 новые версии",
      "паки: acme-thesis",
    ]);
  });

  it("отказ: текст кода ошибки", () => {
    expect(eventSummary(event(2))).toEqual([
      "В репозитории нет такого тега, ветки или коммита.",
    ]);
  });

  it("добавление: адрес и ref как есть", () => {
    expect(eventSummary(event(3))).toEqual([
      "url: https://git.example.org/acme/packs.git",
      "ref: v2026.1.1",
    ]);
  });

  it("препятствия проверки словами", () => {
    expect(
      eventSummary({
        ...event(1),
        summary: { new: 0, blockers: ["no_packs"], packs: [] },
      }),
    ).toEqual([
      "0 новых версий",
      "В ревизии нет паков. Проверьте папку паков.",
    ]);
  });
});
