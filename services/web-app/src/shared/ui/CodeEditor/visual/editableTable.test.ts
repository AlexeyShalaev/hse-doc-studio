import { describe, expect, it } from "vitest";
import {
  addColumn,
  addRow,
  moveColumn,
  parseEditableTable,
  removeColumn,
  removeRow,
  serializeEditableTable,
  setCellValue,
  setColumnAlign,
  setColumnLabel,
  type ParsedEditableTable,
} from "./editableTable";

const REQUIREMENTS = String.raw`\begin{longtable}{|l|>{\raggedright\arraybackslash}p{0.28\textwidth}|>{\raggedright\arraybackslash}p{0.28\textwidth}|>{\centering\arraybackslash}p{0.22\textwidth}|}
\caption{Требования к функциональным характеристикам системы} \label{tab:requirements} \\
\hline
\textbf{№} & \textbf{Пользовательская история} & \textbf{Требование} & \textbf{Область} \\
\hline
\endfirsthead
\multicolumn{4}{l}{Продолжение таблицы \thetable} \\
\hline
\textbf{№} & \textbf{Пользовательская история} & \textbf{Требование} & \textbf{Область} \\
\hline
\endhead
\hline
\endfoot
\hline
\endlastfoot
ТЗ-Ф-01 & Как пользователь, я~хочу \ldots, чтобы \ldots & \req{ТЗ-Ф-01}{Система должна …} & \ldots \\
\hline
ТЗ-Ф-02 & Как пользователь, я~хочу \ldots, чтобы \ldots & \req{ТЗ-Ф-02}{Система должна …} & \ldots \\
\hline
\end{longtable}`;

const parsed = (source: string): ParsedEditableTable => {
  const result = parseEditableTable(source);
  if (!result) throw new Error("expected a table");
  return result;
};

describe("parseEditableTable", () => {
  it("returns null when there is no table", () => {
    expect(parseEditableTable(undefined)).toBeNull();
    expect(parseEditableTable("Просто текст")).toBeNull();
  });

  it("parses the requirements longtable into scaffold + draft", () => {
    const { scaffold, draft } = parsed(REQUIREMENTS);
    expect(scaffold.editable).toBe(true);
    expect(scaffold.canEditColumns).toBe(true);
    expect(draft.columns).toHaveLength(4);
    expect(draft.columns.map((c) => c.label)).toEqual([
      "№",
      "Пользовательская история",
      "Требование",
      "Область",
    ]);
    expect(draft.columns.map((c) => c.align)).toEqual([
      "left",
      "left",
      "left",
      "center",
    ]);
    expect(draft.columns[2]?.template).toEqual({ kind: "req" });
    expect(draft.rows).toHaveLength(2);
    expect(draft.rows[0]?.map((cell) => cell.value)).toEqual([
      "ТЗ-Ф-01",
      "Как пользователь, я~хочу \\ldots, чтобы \\ldots",
      "Система должна …",
      "\\ldots",
    ]);
  });
});

describe("serializeEditableTable", () => {
  it("round-trips an untouched requirements table", () => {
    const { scaffold, draft } = parsed(REQUIREMENTS);
    const output = serializeEditableTable(scaffold, draft);
    expect(output).toContain(
      "\\begin{longtable}{|l|>{\\raggedright\\arraybackslash}p{0.28\\textwidth}|",
    );
    expect(output).toContain("\\endlastfoot");
    expect(output).toContain(
      "\\multicolumn{4}{l}{Продолжение таблицы \\thetable}",
    );
    expect(output).toContain(
      "\\textbf{№} & \\textbf{Пользовательская история}",
    );
    expect(output).toContain("\\req{ТЗ-Ф-01}{Система должна …}");
    expect(output).toContain("Как пользователь, я~хочу \\ldots, чтобы \\ldots");
    expect(output.trimEnd().endsWith("\\end{longtable}")).toBe(true);
  });

  it("keeps inline formatting written into a cell", () => {
    const { scaffold, draft } = parsed(REQUIREMENTS);
    const next = setCellValue(
      draft,
      0,
      2,
      "Система \\textbf{обязана} работать",
    );
    expect(serializeEditableTable(scaffold, next)).toContain(
      "\\req{ТЗ-Ф-01}{Система \\textbf{обязана} работать}",
    );
  });

  it("syncs the \\req id with the first column", () => {
    const { scaffold, draft } = parsed(REQUIREMENTS);
    const next = setCellValue(draft, 0, 0, "ТЗ-Ф-42");
    const output = serializeEditableTable(scaffold, next);
    expect(output).toContain("\\req{ТЗ-Ф-42}{Система должна …}");
    expect(output).not.toContain("\\req{ТЗ-Ф-01}");
  });

  it("adds and removes rows", () => {
    const { scaffold, draft } = parsed(REQUIREMENTS);
    const added = setCellValue(addRow(draft), 2, 0, "ТЗ-Ф-03");
    expect(serializeEditableTable(scaffold, added)).toContain("ТЗ-Ф-03 &");
    const removed = removeRow(draft, 1);
    expect(serializeEditableTable(scaffold, removed)).not.toContain("ТЗ-Ф-02");
  });
});

describe("column operations", () => {
  it("adds a column: spec, header and every data row grow", () => {
    const { scaffold, draft } = parsed(REQUIREMENTS);
    const next = setColumnLabel(addColumn(draft, 4), 4, "Приоритет");
    expect(next.columns).toHaveLength(5);
    const output = serializeEditableTable(scaffold, next);
    expect(output).toContain("\\multicolumn{5}{l}");
    expect(output).toContain("\\textbf{Приоритет}");
    // Every data row now has five cells (four separators).
    const dataRow = output
      .split("\n")
      .find((line) => line.startsWith("ТЗ-Ф-01"));
    expect(dataRow?.match(/&/g)).toHaveLength(4);
  });

  it("removes a column from the spec, header and rows", () => {
    const { scaffold, draft } = parsed(REQUIREMENTS);
    const output = serializeEditableTable(scaffold, removeColumn(draft, 3));
    expect(output).toContain("\\multicolumn{3}{l}");
    expect(output).not.toContain("\\textbf{Область}");
  });

  it("moves a column, reordering the header and rows together", () => {
    const { scaffold, draft } = parsed(REQUIREMENTS);
    const output = serializeEditableTable(scaffold, moveColumn(draft, 3, 0));
    // «Область» moved to the front of both the header and the data rows.
    expect(output).toContain("\\textbf{Область} & \\textbf{№}");
    expect(output).toContain("\\ldots & ТЗ-Ф-01 &");
    // The \req id still tracks the (relocated) «№» column, not the new column 0.
    expect(output).toContain("\\req{ТЗ-Ф-01}{Система должна …}");
  });

  it("changes a column's alignment in the spec", () => {
    const { scaffold, draft } = parsed(REQUIREMENTS);
    const output = serializeEditableTable(
      scaffold,
      setColumnAlign(draft, 0, "center"),
    );
    expect(output).toContain("\\begin{longtable}{|c|");
  });
});

describe("round-trip regressions (from adversarial review)", () => {
  it("keeps the \\req id when the id column is deleted", () => {
    const { scaffold, draft } = parsed(REQUIREMENTS);
    const output = serializeEditableTable(scaffold, removeColumn(draft, 0));
    expect(output).toContain("\\req{ТЗ-Ф-01}{Система должна …}");
    expect(output).not.toContain("\\req{}");
  });

  it("emits a plain \\req id even if the id cell is formatted", () => {
    const { scaffold, draft } = parsed(REQUIREMENTS);
    const next = setCellValue(draft, 0, 0, "\\textbf{ТЗ-Ф-01}");
    const output = serializeEditableTable(scaffold, next);
    expect(output).toContain("\\req{ТЗ-Ф-01}{Система должна …}");
    expect(output).not.toContain("\\req{\\textbf");
  });

  it("does not inject \\hline into a borderless table", () => {
    const src = [
      "\\begin{tabular}{cc}",
      "1 & 2 \\\\",
      "3 & 4 \\\\",
      "\\end{tabular}",
    ].join("\n");
    const { scaffold, draft } = parsed(src);
    const output = serializeEditableTable(scaffold, draft);
    expect(output).not.toContain("\\hline");
    expect(output).toContain("1 & 2 \\\\");
  });

  it("preserves a deliberate partial-span \\multicolumn", () => {
    const src = REQUIREMENTS.replace(
      "\\multicolumn{4}{l}",
      "\\multicolumn{2}{l}",
    );
    const { scaffold, draft } = parsed(src);
    expect(serializeEditableTable(scaffold, draft)).toContain(
      "\\multicolumn{2}{l}",
    );
  });

  it("preserves nested formatting in an unchanged header", () => {
    const src = [
      "\\begin{tabular}{ll}",
      "\\hline",
      "\\textbf{Плановая \\textit{дата}} & \\textbf{B} \\\\",
      "\\hline",
      "x & y \\\\",
      "\\hline",
      "\\end{tabular}",
    ].join("\n");
    const { scaffold, draft } = parsed(src);
    expect(serializeEditableTable(scaffold, draft)).toContain(
      "\\textbf{Плановая \\textit{дата}}",
    );
  });

  it("preserves \\\\[dim] and \\\\* row-break suffixes without leaking the *", () => {
    const src = [
      "\\begin{tabular}{ll}",
      "a & b \\\\[6pt]",
      "c & d \\\\*",
      "e & f \\\\",
      "\\end{tabular}",
    ].join("\n");
    const { scaffold, draft } = parsed(src);
    expect(draft.rows.map((row) => row.map((cell) => cell.value))).toEqual([
      ["a", "b"],
      ["c", "d"],
      ["e", "f"],
    ]);
    const output = serializeEditableTable(scaffold, draft);
    expect(output).toContain("a & b \\\\[6pt]");
    expect(output).toContain("c & d \\\\*");
  });

  it("drops the orphaned separator when deleting column 0", () => {
    const src = [
      "\\begin{tabular}{l|cc}",
      "1 & 2 & 3 \\\\",
      "\\end{tabular}",
    ].join("\n");
    const { scaffold, draft } = parsed(src);
    const output = serializeEditableTable(scaffold, removeColumn(draft, 0));
    expect(output).toContain("\\begin{tabular}{cc}");
    expect(output).not.toContain("{|cc}");
  });
});

describe("round-trip regressions (second pass)", () => {
  it("keeps each \\req column's own id in a two-req-column row", () => {
    const src = [
      "\\begin{tabular}{lll}",
      "X-1 & \\req{X-1}{aa} & \\req{X-9}{bb} \\\\",
      "\\end{tabular}",
    ].join("\n");
    const { scaffold, draft } = parsed(src);
    const output = serializeEditableTable(scaffold, draft);
    expect(output).toContain("\\req{X-1}{aa}");
    expect(output).toContain("\\req{X-9}{bb}");
  });

  it("keeps the id when column 0 is itself the \\req column", () => {
    const src = [
      "\\begin{tabular}{ll}",
      "\\req{ТЗ-1}{aa} & X \\\\",
      "\\req{ТЗ-2}{bb} & Y \\\\",
      "\\end{tabular}",
    ].join("\n");
    const { scaffold, draft } = parsed(src);
    const output = serializeEditableTable(scaffold, draft);
    expect(output).toContain("\\req{ТЗ-1}{aa}");
    expect(output).toContain("\\req{ТЗ-2}{bb}");
  });

  it("parses tabular* with its mandatory width argument", () => {
    const src = [
      "\\begin{tabular*}{\\linewidth}{@{\\extracolsep{\\fill}}ll}",
      "a & b \\\\",
      "\\end{tabular*}",
    ].join("\n");
    const { scaffold, draft } = parsed(src);
    expect(draft.columns).toHaveLength(2);
    const output = serializeEditableTable(scaffold, draft);
    expect(output).toContain(
      "\\begin{tabular*}{\\linewidth}{@{\\extracolsep{\\fill}}ll}",
    );
    expect(output).toContain("a & b");
  });

  it("keeps a borderless bold-header table borderless", () => {
    const src = [
      "\\begin{tabular}{ll}",
      "\\textbf{K} & \\textbf{V} \\\\",
      "a & b \\\\",
      "c & d \\\\",
      "\\end{tabular}",
    ].join("\n");
    const { scaffold, draft } = parsed(src);
    expect(draft.rows.map((row) => row.map((cell) => cell.value))).toEqual([
      ["a", "b"],
      ["c", "d"],
    ]);
    const output = serializeEditableTable(scaffold, draft);
    expect(output).not.toContain("\\hline");
    expect(output).toContain("\\textbf{K} & \\textbf{V}");
  });

  it("preserves a partial \\cline instead of forcing full rules", () => {
    const src = [
      "\\begin{tabular}{lll}",
      "a & b & c \\\\ \\cline{2-3}",
      "d & e & f \\\\",
      "\\end{tabular}",
    ].join("\n");
    const { scaffold, draft } = parsed(src);
    const output = serializeEditableTable(scaffold, draft);
    expect(output).toContain("\\cline{2-3}");
    expect(output).not.toContain("\\hline");
  });
});

describe("round-trip regressions (convergence pass)", () => {
  it("links and syncs a \\req id that contains a tilde", () => {
    const src = [
      "\\begin{tabular}{ll}",
      "ТЗ~1 & \\req{ТЗ~1}{aa} \\\\",
      "\\end{tabular}",
    ].join("\n");
    const { scaffold, draft } = parsed(src);
    // Untouched: the \req id survives verbatim.
    expect(serializeEditableTable(scaffold, draft)).toContain(
      "\\req{ТЗ~1}{aa}",
    );
    // Renaming the id column re-syncs the linked \req id.
    const renamed = setCellValue(draft, 0, 0, "ТЗ~9");
    expect(serializeEditableTable(scaffold, renamed)).toContain(
      "\\req{ТЗ~9}{aa}",
    );
  });

  it("degrades a \\cline to \\hline when a column is removed", () => {
    const src = [
      "\\begin{tabular}{lll}",
      "a & b & c \\\\ \\cline{2-3}",
      "d & e & f \\\\",
      "\\end{tabular}",
    ].join("\n");
    const { scaffold, draft } = parsed(src);
    const output = serializeEditableTable(scaffold, removeColumn(draft, 0));
    expect(output).not.toContain("\\cline");
    expect(output).toContain("\\begin{tabular}{ll}");
  });

  it("does not drop an interior rule-only row", () => {
    const src = [
      "\\begin{tabular}{ll}",
      "a & b \\\\",
      "\\hline \\\\",
      "\\hline",
      "\\end{tabular}",
    ].join("\n");
    const { scaffold, draft } = parsed(src);
    const output = serializeEditableTable(scaffold, draft);
    expect((output.match(/\\hline/g) ?? []).length).toBeGreaterThanOrEqual(2);
  });
});

describe("round-trip regressions (fourth pass)", () => {
  // A trailing partial rule after the LAST `\\` folds into finalRule (not
  // rowRules); a column op must still degrade its now-out-of-range \cline.
  it("degrades a trailing \\cline (finalRule) when a column is removed", () => {
    const src = [
      "\\begin{tabular}{lll}",
      "a & b & c \\\\",
      "d & e & f \\\\ \\cline{2-3}",
      "\\end{tabular}",
    ].join("\n");
    const { scaffold, draft } = parsed(src);
    // Untouched: the trailing \cline round-trips verbatim.
    expect(serializeEditableTable(scaffold, draft)).toContain("\\cline{2-3}");
    // After removing a column, no stale out-of-range \cline may survive.
    const output = serializeEditableTable(scaffold, removeColumn(draft, 0));
    expect(output).not.toContain("\\cline");
    expect(output).toContain("\\begin{tabular}{ll}");
  });

  it("degrades a trailing \\cline (finalRule) when a column is added", () => {
    const src = [
      "\\begin{tabular}{ll}",
      "a & b \\\\ \\cline{1-2}",
      "\\end{tabular}",
    ].join("\n");
    const { scaffold, draft } = parsed(src);
    const output = serializeEditableTable(scaffold, addColumn(draft, 2));
    expect(output).not.toContain("\\cline");
  });
});

describe("plain tabular", () => {
  const TABULAR = String.raw`\begin{tabular}{ll}
\hline
\textbf{Ключ} & \textbf{Значение} \\
\hline
A & 1 \\
B & 2 \\
\hline
\end{tabular}`;

  it("lifts the bold header into labels and keeps data rows editable", () => {
    const { scaffold, draft } = parsed(TABULAR);
    expect(draft.columns.map((c) => c.label)).toEqual(["Ключ", "Значение"]);
    expect(draft.rows.map((row) => row.map((cell) => cell.value))).toEqual([
      ["A", "1"],
      ["B", "2"],
    ]);
    const output = serializeEditableTable(
      scaffold,
      setCellValue(draft, 0, 1, "10"),
    );
    expect(output).toContain("\\textbf{Ключ} & \\textbf{Значение}");
    expect(output).toContain("A & 10");
  });
});
