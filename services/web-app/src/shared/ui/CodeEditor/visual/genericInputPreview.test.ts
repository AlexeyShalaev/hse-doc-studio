import { describe, expect, it } from "vitest";
import { parseGenericInputPreview } from "./genericInputPreview";

describe("parseGenericInputPreview", () => {
  it("returns an empty safe fallback while a source is unavailable", () => {
    expect(parseGenericInputPreview(undefined)).toEqual({
      lineCount: 0,
      sectionCount: 0,
      tableCount: 0,
      listCount: 0,
      snippets: [],
    });
    expect(parseGenericInputPreview("")).toEqual(
      parseGenericInputPreview(undefined),
    );
  });

  it("counts real document structures without double-counting table wrappers", () => {
    const source = String.raw`\section*{Обзор}
\begin{table}
  \begin{tabular}{ll}
    A & B \\
  \end{tabular}
\end{table}
\begin{longtable}{ll}
  A & B \\
\end{longtable}
\begin{itemize}
  \item Первый пункт
  \begin{enumerate}
    \item Вложенный пункт
  \end{enumerate}
\end{itemize}`;

    const preview = parseGenericInputPreview(source);
    expect(preview.sectionCount).toBe(1);
    expect(preview.tableCount).toBe(2);
    expect(preview.listCount).toBe(2);
    expect(preview.lineCount).toBe(source.split("\n").length);
  });

  it("ignores comments and projects common printable LaTeX to plain text", () => {
    const source = String.raw`% \section{Ложный раздел}
\section*{\textbf{Введение \& цели \ldots}}
% \begin{table} also ignored
Первый~абзац с \emph{важным \textit{текстом}}, готов на 100\%.
\subsection[Коротко]{Подробности}
\begin{description}
\item Термин \#1 и поле user\_id.
\end{description}`;

    const preview = parseGenericInputPreview(source);
    expect(preview.sectionCount).toBe(2);
    expect(preview.tableCount).toBe(0);
    expect(preview.listCount).toBe(1);
    expect(preview.snippets).toContain("Введение & цели …");
    expect(preview.snippets).toContain(
      "Первый абзац с важным текстом, готов на 100%.",
    );
    expect(preview.snippets).toContain("Подробности");
    expect(preview.snippets).toContain("Термин #1 и поле user_id.");
    expect(preview.snippets.join(" ")).not.toContain("Ложный раздел");
  });

  it("uses captions and printable prose but skips setup and raw table rows", () => {
    const source = String.raw`\usepackage{longtable}
\newcommand{\internal}{Не показывать как текст}
\begin{longtable}{ll}
\caption{Требования к системе} \\
ID & Требование \\
ТЗ-Ф-01 & Система должна работать \\
\end{longtable}

После таблицы приведено пояснение.`;

    const preview = parseGenericInputPreview(source);
    expect(preview.tableCount).toBe(1);
    expect(preview.snippets).toEqual([
      "Требования к системе",
      "После таблицы приведено пояснение.",
    ]);
  });

  it("tolerates malformed TeX without expanding or executing commands", () => {
    const source = String.raw`\section{Незакрытый заголовок
Обычный текст с \textbf{незакрытой обёрткой
\begin{itemize}
\item Последняя строка`;

    expect(() => parseGenericInputPreview(source)).not.toThrow();
    const preview = parseGenericInputPreview(source);
    expect(preview.lineCount).toBe(4);
    expect(preview.sectionCount).toBe(1);
    expect(preview.listCount).toBe(1);
    expect(
      preview.snippets.every((snippet) => typeof snippet === "string"),
    ).toBe(true);
  });

  it("returns unknown-command content only as inert strings", () => {
    const preview = parseGenericInputPreview(
      String.raw`\unknown{<img src=x onerror=alert(1)> Безопасный текст}`,
    );

    expect(preview.snippets).toEqual([
      "<img src=x onerror=alert(1)> Безопасный текст",
    ]);
    expect(typeof preview.snippets[0]).toBe("string");
  });

  it("bounds both snippet count and snippet length", () => {
    const source = Array.from(
      { length: 12 },
      (_, index) =>
        `Абзац ${String(index + 1)} ${"очень длинный текст ".repeat(12)}`,
    ).join("\n\n");

    const preview = parseGenericInputPreview(source);
    expect(preview.snippets).toHaveLength(6);
    expect(
      preview.snippets.every((snippet) => Array.from(snippet).length <= 120),
    ).toBe(true);
    expect(preview.snippets.every((snippet) => snippet.endsWith("…"))).toBe(
      true,
    );
  });
});
