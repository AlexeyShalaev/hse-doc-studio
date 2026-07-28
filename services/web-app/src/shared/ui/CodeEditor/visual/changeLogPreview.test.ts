import { describe, expect, it } from "vitest";
import { parseChangeLogPreview } from "./changeLogPreview";

describe("parseChangeLogPreview", () => {
  it("uses a faithful twenty-row fallback while the include is loading", () => {
    const preview = parseChangeLogPreview(undefined);
    expect(preview.title).toBe("ЛИСТ РЕГИСТРАЦИИ ИЗМЕНЕНИЙ");
    expect(preview.rows).toHaveLength(20);
    expect(preview.rows.every((row) => row.length === 10)).toBe(true);
  });

  it("reads the real title, row count, and filled cells", () => {
    const source = String.raw`
      \section*{ЛИСТ РЕГИСТРАЦИИ ИЗМЕНЕНИЙ}
      \begin{tabularx}{\textwidth}{|X|X|}
      \multicolumn{10}{|c|}{Лист регистрации изменений} \\
      Изм. & Измененных & Замененных & Новых & Аннулированных & Всего & № документа & Входящий & Подп. & Дата \\
      \hline
      1 & 2 & & 3 & & 42 & АБВГ.01 & вх. 7 & Иванов & 18.07.26 \\[0.45cm] \hline
       & & & & & & & & & \\[0.45cm] \hline
      \end{tabularx}
    `;

    const preview = parseChangeLogPreview(source);
    expect(preview.tableTitle).toBe("Лист регистрации изменений");
    expect(preview.rows).toHaveLength(2);
    expect(preview.rows[0]).toEqual([
      "1",
      "2",
      "",
      "3",
      "",
      "42",
      "АБВГ.01",
      "вх. 7",
      "Иванов",
      "18.07.26",
    ]);
  });

  it("falls back safely when a custom file has no recognizable body", () => {
    expect(parseChangeLogPreview("\\section*{Другой лист}").rows).toHaveLength(
      20,
    );
  });
});
