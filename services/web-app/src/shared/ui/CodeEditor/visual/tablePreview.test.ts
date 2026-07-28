import { describe, expect, it } from "vitest";
import { parseTablePreview } from "./tablePreview";

describe("parseTablePreview", () => {
  it("returns a safe fallback for missing or malformed source", () => {
    expect(parseTablePreview(undefined)).toEqual({
      caption: null,
      headers: [],
      rows: [],
    });
    expect(parseTablePreview("\\begin{tabular}{broken")).toEqual({
      caption: null,
      headers: [],
      rows: [],
    });
  });

  it("parses an outer table with an inner tabular and caption", () => {
    const source = String.raw`
      \begin{table}[H]
      \centering
      \caption[Краткое]{Сравнение \textbf{подходов}}
      \label{tab:comparison}
      \begin{tabular}{lll}
      \hline
      \textbf{Метод} & \textbf{Статус} & \textbf{Комментарий} \\
      \hline
      Первый & \cmpplus & \emph{Подходит} \\
      Второй & \cmpminus & Не подходит \\
      \hline
      \end{tabular}
      \end{table}
    `;

    expect(parseTablePreview(source)).toEqual({
      caption: "Сравнение подходов",
      headers: ["Метод", "Статус", "Комментарий"],
      rows: [
        ["Первый", "+", "Подходит"],
        ["Второй", "−", "Не подходит"],
      ],
    });
  });

  it("handles standalone tabularx, multiline cells, comments, and spacing", () => {
    const source = String.raw`
      % fake & row \\
      \begin{tabularx}{\textwidth}{lXX}
      \textbf{Код} & \textbf{Описание} & \textbf{План} \\
      A\&B & Первая строка
        \newline вторая~строка & \cmpplanned \\[0.45cm]
      C & Значение \ldots & Готово % ignored & fake \\
        \\
      \end{tabularx}
    `;

    expect(parseTablePreview(source)).toEqual({
      caption: null,
      headers: ["Код", "Описание", "План"],
      rows: [
        ["A&B", "Первая строка вторая строка", "±"],
        ["C", "Значение …", "Готово"],
      ],
    });
  });

  it("omits hline/cline geometry and keeps multicolumn printable text", () => {
    const source = String.raw`
      \begin{tabular}{lll}
      \textbf{A} & \textbf{B} & \textbf{C} \\
      \cline{1-3}
      \multicolumn{2}{c}{Общий {текст}} & 42 \\
      \hline
      X & Y & Z \\
      \end{tabular}
    `;

    expect(parseTablePreview(source)).toEqual({
      caption: null,
      headers: ["A", "B", "C"],
      rows: [
        ["Общий текст", "42"],
        ["X", "Y", "Z"],
      ],
    });
  });

  it("keeps every row as data when no row is bold-heavy", () => {
    const source = String.raw`
      \begin{tabular}{ll}
      Key & Value \\
      A & 1 \\
      B & 2 \\
      \end{tabular}
    `;

    expect(parseTablePreview(source)).toEqual({
      caption: null,
      headers: [],
      rows: [
        ["Key", "Value"],
        ["A", "1"],
        ["B", "2"],
      ],
    });
  });

  it("excludes repeated longtable headers and control rows", () => {
    const source = String.raw`
      \begin{longtable}{ll}
      \caption{Большая таблица} \\
      \textbf{ID} & \textbf{Текст} \\
      \endfirsthead
      \multicolumn{2}{l}{Продолжение} \\
      \textbf{ID} & \textbf{Текст} \\
      \endhead
      \endfoot
      \endlastfoot
      1 & Один \\
      2 & Два \\
      \end{longtable}
    `;

    expect(parseTablePreview(source)).toEqual({
      caption: "Большая таблица",
      headers: ["ID", "Текст"],
      rows: [
        ["1", "Один"],
        ["2", "Два"],
      ],
    });
  });

  it("bounds columns, rows, and rendered cell length", () => {
    const manyCells = Array.from(
      { length: 15 },
      (_, index) => `C${index}`,
    ).join(" & ");
    const rows = Array.from(
      { length: 110 },
      (_, index) => `${manyCells} ${String(index)} \\\\`,
    ).join("\n");
    const source = `\\begin{tabular}{${"l".repeat(15)}}\n${"x".repeat(
      350,
    )} & short \\\\\n${rows}\n\\end{tabular}`;

    const preview = parseTablePreview(source);
    expect(preview.headers).toEqual([]);
    expect(preview.rows).toHaveLength(100);
    expect(preview.rows.every((row) => row.length <= 12)).toBe(true);
    expect(preview.rows[0]?.[0]).toHaveLength(300);
    expect(preview.rows[0]?.[0]?.endsWith("…")).toBe(true);
  });
});
