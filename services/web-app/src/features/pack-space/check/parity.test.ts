import { readFileSync } from "node:fs";
import { join } from "node:path";
import { describe, expect, it } from "vitest";

// Карта паритета «Проверки» (pack-studio-ux.md, 7.4, принцип P11): каждая функция прежних режимов
// «Матрица», «Атлас» и «Сравнить» есть строкой в карте и закрыта тестом. Тест ломается, если
// строку убрали из карты, а функцию оставили (или наоборот), или если тест, на который она
// ссылается, переименован или удалён.

const DIR = import.meta.dirname;
const DOC = readFileSync(
  join(DIR, "../../../../../../docs/design/pack-studio-ux.md"),
  "utf8",
);
const SOURCES: Record<string, string> = {
  "check.test.tsx": readFileSync(join(DIR, "check.test.tsx"), "utf8"),
  "cases.test.tsx": readFileSync(join(DIR, "cases.test.tsx"), "utf8"),
};

type Row = { was: string; file: keyof typeof SOURCES; test: string };

const ROWS: readonly Row[] = [
  {
    was: "Матрица: окно сценария из строки или клетки",
    file: "cases.test.tsx",
    test: "«Открыть случай» из строки",
  },
  {
    was: "Матрица: окно сценария из строки или клетки",
    file: "cases.test.tsx",
    test: "«Открыть случай» из клетки",
  },
  {
    was: "Матрица: редактор утверждений сценария",
    file: "cases.test.tsx",
    test: "редактор ожиданий: убрать, добавить из предложенного, сохранить",
  },
  {
    was: "Матрица: принять текущий результат как ожидаемый",
    file: "cases.test.tsx",
    test: "«Принять текущий результат как ожидаемый» пишет снимок",
  },
  {
    was: "Матрица: удалить сценарий",
    file: "cases.test.tsx",
    test: "удаление просит подтверждение",
  },
  {
    was: "Матрица: вид «Как студент» у сценария",
    file: "cases.test.tsx",
    test: "«Посмотреть как студент» открывает вид студента",
  },
  {
    was: "Матрица: стрелки, Home и End по таблице",
    file: "cases.test.tsx",
    test: "в Tab-порядке одна клетка; стрелки, Home, End и Ctrl",
  },
  {
    was: "Матрица: выпущенная версия, сценарии для чтения",
    file: "cases.test.tsx",
    test: "выпущенная версия: окно только для чтения",
  },
  {
    was: "Матрица: относительно ожидаемого или основной версии",
    file: "check.test.tsx",
    test: "переключатель «Относительно» пишет `against` в адрес",
  },
  {
    was: "Матрица: прогнать заново",
    file: "cases.test.tsx",
    test: "«Проверить заново» запрашивает таблицу ещё раз",
  },
  {
    was: "Матрица: статусы клеток и буквы групп",
    file: "check.test.tsx",
    test: "таблица: готовые случаи в строках, части результата в столбцах",
  },
  {
    was: "Матрица: показать результат и сравнить",
    file: "check.test.tsx",
    test: "клетка показывает, что в ней, и ведёт к результату или сравнению",
  },
  {
    was: "Атлас: карточки условий и «Зафиксировать»",
    file: "check.test.tsx",
    test: "значение условия фиксируется в адресе и снимается",
  },
  {
    was: "Атлас: слишком много вариантов, что зафиксировать",
    file: "check.test.tsx",
    test: "слишком много вариантов: объяснение и выбор, что зафиксировать",
  },
  {
    was: "Атлас: переключатель «Строки / По результатам»",
    file: "cases.test.tsx",
    test: "переключатель «По сочетаниям» и «По результатам»",
  },
  {
    was: "Атлас: сортировка",
    file: "cases.test.tsx",
    test: "порядок «Сначала частые»",
  },
  {
    was: "Атлас: фильтры по условиям",
    file: "cases.test.tsx",
    test: "фильтр по условию сужает список сочетаний",
  },
  {
    was: "Атлас: фильтр по варианту результата",
    file: "cases.test.tsx",
    test: "«Показать эти сочетания» возвращает к строкам только этого варианта",
  },
  {
    was: "Атлас: пометка «сейчас на экране»",
    file: "cases.test.tsx",
    test: "«Сейчас на экране»: вариант результата для условий экрана",
  },
  {
    was: "Атлас: поиск",
    file: "cases.test.tsx",
    test: "поиск среди вариантов сужает список",
  },
  {
    was: "Атлас: показать результат варианта",
    file: "check.test.tsx",
    test: "все варианты за кнопкой; вариант открывается в «Результате»",
  },
  {
    was: "Сравнить: подписи изменений",
    file: "check.test.tsx",
    test: "подписи изменений словами: роли по-русски",
  },
];

/** Карта паритета 7.4: от заголовка раздела до следующего «##». */
const MAP = (() => {
  const start = DOC.indexOf("### 7.4.");
  const end = DOC.indexOf("\n## ", start);
  return DOC.slice(start, end);
})();

describe("карта паритета «Проверки» (7.4)", () => {
  it("каждая функция есть строкой в карте с «где теперь», кликами и срезом", () => {
    for (const was of new Set(ROWS.map((row) => row.was))) {
      const line = MAP.split("\n").find((item) =>
        item.startsWith(`| ${was} |`),
      );
      expect(line, was).toBeDefined();
      const cells = (line ?? "").split("|").map((cell) => cell.trim());
      // ["", функция, где теперь, клики, срез, ""]
      expect(cells[2], was).not.toBe("");
      expect(cells[3], was).toMatch(/^\d(-\d)?$/);
      expect(cells[4], was).toContain("S10");
    }
  });

  it("в карте нет строк о Матрице, Атласе и Сравнить, которых не знает тест (дыр нет в обе стороны)", () => {
    const known = new Set(ROWS.map((row) => row.was));
    const listed = MAP.split("\n")
      .map(
        (line) => /^\| ((?:Матрица|Атлас|Сравнить): [^|]+?) \|/.exec(line)?.[1],
      )
      .filter((was): was is string => was !== undefined);
    expect(listed.length).toBeGreaterThanOrEqual(known.size);
    expect(listed.filter((was) => !known.has(was))).toEqual([]);
  });

  it("каждая строка закрыта тестом: он есть в файле и называется как в списке", () => {
    for (const row of ROWS) {
      const source = SOURCES[row.file] ?? "";
      expect(source, `${row.was}: ${row.test}`).toContain(row.test);
    }
  });

  it("у каждой функции хотя бы один тест, а их число не меньше числа функций", () => {
    const withTests = new Set(ROWS.map((row) => row.was));
    expect(withTests.size).toBe(21);
    expect(ROWS.length).toBeGreaterThanOrEqual(withTests.size);
  });
});
