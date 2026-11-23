import { describe, expect, it } from "vitest";

// Классы сравнения (`cmp-*`, `po-*` из outcome.css, rules.css, modes.css) живут в этой папке. Компонент,
// который их рисует, сам подключает `compare/styles`: иначе экран, открытый напрямую (например,
// «Проверка» с `compare=1`), остаётся без стилей, пока где-то ещё не загрузится панель «Изменения».
const sources = import.meta.glob<string>("../../**/*.tsx", {
  query: "?raw",
  import: "default",
  eager: true,
});

const USES_COMPARE_CLASSES =
  /className=\{?[^}>]*?["'`][^"'`]*\b(cmp(-[a-z-]+)?|po-(notice|skeleton|chain|fact|filter-select|link|mono|note)[a-z-]*)\b/;
const IMPORTS_STYLES = /import\s+["'][./]*(check\/)?compare\/styles["'];|import\s+["']\.\/styles["'];/;

describe("стили сравнения", () => {
  const users = Object.entries(sources).filter(
    ([path, text]) =>
      !/\.test\.tsx$|gallery/.test(path) && USES_COMPARE_CLASSES.test(text),
  );

  it("находит компоненты сравнения", () => {
    expect(users.map(([path]) => path)).toEqual(
      expect.arrayContaining([
        "./CompareMode.tsx",
        "./ChangeList.tsx",
        "../../changes/impact/VersionImpact.tsx",
      ]),
    );
  });

  it.each(users.map(([path, text]) => [path, text]))(
    "%s подключает compare/styles",
    (_path, text) => {
      expect(text).toMatch(IMPORTS_STYLES);
    },
  );
});
