import { describe, expect, it } from "vitest";
import type { HelpMap } from "../api/helpApi";
import { rankHelpKeys } from "./matchHelpRoute";

const article = (key: string, routes: string[]) => ({
  key,
  title: key,
  summary: "",
  url: `/help/ru/${key}/`,
  access: "user" as const,
  routes,
});

const map = (articles: ReturnType<typeof article>[]): HelpMap => {
  const routes: Record<string, string[]> = {};
  for (const a of articles)
    for (const r of a.routes) (routes[r] ??= []).push(a.key);
  return { routes, articles };
};

describe("справка экрана: подбор статьи по маршруту", () => {
  const help = map([
    article("runbooks/editor-preview", [
      "/projects/:projectId/documents/:docId",
    ]),
    article("runbooks/checks", [
      "/projects/:projectId/documents/:docId?tab=checks",
    ]),
    article("runbooks/submit-sign", [
      "/projects/:projectId/submit",
      "/projects/:projectId/documents/:docId?tab=signatures",
    ]),
    article("runbooks/ai-agent", ["/settings/providers"]),
    article("runbooks/build", ["/settings/:section"]),
  ]);

  it("шаблон пути находит статью экрана", () => {
    expect(rankHelpKeys(help, "/projects/p1/submit", "")).toEqual([
      "runbooks/submit-sign",
    ]);
  });

  it("вкладка в адресе ставит свою статью первой", () => {
    expect(
      rankHelpKeys(help, "/projects/p1/documents/thesis", "?tab=checks"),
    ).toEqual(["runbooks/checks", "runbooks/editor-preview"]);
  });

  it("маршрут с чужой вкладкой не подходит", () => {
    expect(
      rankHelpKeys(help, "/projects/p1/documents/thesis", "?tab=compile"),
    ).toEqual(["runbooks/editor-preview"]);
  });

  it("конкретный раздел и общий шаблон: статья, где маршрут первый, впереди", () => {
    expect(rankHelpKeys(help, "/settings/providers", "")).toEqual([
      "runbooks/ai-agent",
      "runbooks/build",
    ]);
  });

  it("экран без статьи даёт пустой список", () => {
    expect(rankHelpKeys(help, "/inbox", "")).toEqual([]);
  });
});
