const DEFAULT_ROW_COUNT = 20;
const COLUMN_COUNT = 10;

export type ChangeLogPreview = {
  title: string;
  tableTitle: string;
  rows: string[][];
};

const emptyRows = (count = DEFAULT_ROW_COUNT): string[][] =>
  Array.from({ length: count }, () => Array<string>(COLUMN_COUNT).fill(""));

const stripSimpleLatex = (value: string): string => {
  let text = value.trim();
  // Preserve the body of common one-argument text commands. Repeating handles
  // shallow nesting without pretending to be a full TeX interpreter.
  for (let pass = 0; pass < 4; pass += 1) {
    const next = text.replace(
      /\\(?:textbf|textit|emph|underline|textrm|textsf|texttt|makecell)\*?\{([^{}]*)\}/g,
      "$1",
    );
    if (next === text) break;
    text = next;
  }
  return text
    .replace(/\\\\/g, " ")
    .replace(/\\([%&#_$])/g, "$1")
    .replace(/~/g, " ")
    .replace(/\\[A-Za-z@]+\*?/g, "")
    .replace(/[{}]/g, "")
    .replace(/\s+/g, " ")
    .trim();
};

const splitCells = (row: string): string[] => {
  const cells: string[] = [];
  let start = 0;
  let braceDepth = 0;

  for (let cursor = 0; cursor < row.length; cursor += 1) {
    const character = row.charAt(cursor);
    if (character === "\\") {
      cursor += 1;
      continue;
    }
    if (character === "{") braceDepth += 1;
    if (character === "}" && braceDepth > 0) braceDepth -= 1;
    if (character !== "&" || braceDepth !== 0) continue;
    cells.push(stripSimpleLatex(row.slice(start, cursor)));
    start = cursor + 1;
  }
  cells.push(stripSimpleLatex(row.slice(start)));
  return cells;
};

/**
 * Read the printable body of the pack's registration sheet. The visual widget
 * uses the real included source for row count and filled cell values, while
 * the complex tabularx geometry remains a semantic HTML preview.
 */
export const parseChangeLogPreview = (
  source: string | undefined,
): ChangeLogPreview => {
  const title = stripSimpleLatex(
    /\\section\*\s*\{([^{}]*)\}/.exec(source ?? "")?.[1] ??
      "ЛИСТ РЕГИСТРАЦИИ ИЗМЕНЕНИЙ",
  );
  const tableTitle = stripSimpleLatex(
    /\\multicolumn\s*\{10\}\s*\{[^{}]*\}\s*\{([^{}]*)\}/.exec(
      source ?? "",
    )?.[1] ?? "Лист регистрации изменений",
  );
  if (!source) return { title, tableTitle, rows: emptyRows() };

  const rows: string[][] = [];
  let insideTable = false;
  let afterHeader = false;

  for (const line of source.split(/\r?\n/)) {
    if (/\\begin\{tabularx?\}/.test(line)) {
      insideTable = true;
      continue;
    }
    if (!insideTable) continue;
    if (/\\end\{tabularx?\}/.test(line)) break;
    if (!afterHeader) {
      if (/^\s*Изм\.\s*&/.test(line)) afterHeader = true;
      continue;
    }

    const printable = /^(.*?)\\\\(?:\[[^\]]*\])?\s*\\hline\s*$/.exec(line)?.[1];
    if (printable === undefined) continue;
    const cells = splitCells(printable);
    if (cells.length === COLUMN_COUNT) rows.push(cells);
  }

  return {
    title,
    tableTitle,
    rows: rows.length > 0 ? rows : emptyRows(),
  };
};
