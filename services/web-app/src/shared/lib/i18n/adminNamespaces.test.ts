import { describe, expect, it } from "vitest";
import { loadAdminNamespaces } from "./adminNamespaces";
import { i18n } from "./init";

describe("loadAdminNamespaces", () => {
  it("грузит только запрошенные словари, оба языка", async () => {
    expect(i18n.hasResourceBundle("ru", "adminStorage")).toBe(false);
    await loadAdminNamespaces(["storage"]);
    expect(i18n.hasResourceBundle("ru", "adminStorage")).toBe(true);
    expect(i18n.hasResourceBundle("en", "adminStorage")).toBe(true);
    expect(i18n.hasResourceBundle("ru", "adminServices")).toBe(false);
  });

  it("повторный вызов возвращает готовый результат без перезагрузки", async () => {
    await loadAdminNamespaces(["services"]);
    const bundle = i18n.getResourceBundle("ru", "adminServices");
    await loadAdminNamespaces(["services"]);
    expect(i18n.getResourceBundle("ru", "adminServices")).toBe(bundle);
  });
});
