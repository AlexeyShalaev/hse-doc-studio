const MAX_SNIPPETS = 6;
const MAX_SNIPPET_LENGTH = 120;
const MAX_CANDIDATES = MAX_SNIPPETS * 4;

const SECTION_COMMANDS = new Set([
  "part",
  "chapter",
  "section",
  "subsection",
  "subsubsection",
  "paragraph",
  "subparagraph",
]);

const TABLE_ENVIRONMENTS = new Set([
  "table",
  "table*",
  "longtable",
  "tabular",
  "tabular*",
  "tabularx",
  "tabulary",
]);

const LIST_ENVIRONMENTS = new Set([
  "itemize",
  "enumerate",
  "description",
  "list",
]);

const TEXT_WRAPPERS =
  /\\(?:textbf|textit|emph|underline|textrm|textsf|texttt|textsc|mbox|makecell|MakeUppercase|MakeLowercase)\*?\s*\{([^{}]*)\}/g;

const SKIPPED_LINE_COMMANDS =
  /^(?:\\(?:begin|end|hline|cline|clearpage|newpage|pagebreak|input|include|documentclass|usepackage|RequirePackage|newcommand|renewcommand|providecommand|DeclareRobustCommand|NewDocumentCommand|ProvideDocumentCommand|def|let|setlength|addtolength|titleformat|titlespacing|captionsetup|pagestyle|thispagestyle|pagenumbering|addcontentsline|label|vspace|hspace|vfill|hfill|centering|raggedright|raggedleft|sloppy|fancyhead|fancyfoot|fancyhf|renewenvironment|newenvironment|includegraphics|rule|rotatebox|raisebox|multicolumn|multirow)\b|[{}[\]&]+$)/;

export type GenericInputPreview = {
  lineCount: number;
  sectionCount: number;
  tableCount: number;
  listCount: number;
  snippets: string[];
};

type Candidate = {
  offset: number;
  priority: number;
  text: string;
};

type BalancedValue = {
  value: string;
  end: number;
};

const emptyPreview = (lineCount = 0): GenericInputPreview => ({
  lineCount,
  sectionCount: 0,
  tableCount: 0,
  listCount: 0,
  snippets: [],
});

const countLines = (source: string): number => {
  if (source.length === 0) return 0;
  let count = 1;
  for (let cursor = 0; cursor < source.length; cursor += 1) {
    const character = source.charAt(cursor);
    if (character === "\n") count += 1;
    if (character === "\r" && source.charAt(cursor + 1) !== "\n") count += 1;
  }
  return count;
};

const isEscapedAt = (source: string, index: number): boolean => {
  let slashCount = 0;
  for (let cursor = index - 1; cursor >= 0; cursor -= 1) {
    if (source.charAt(cursor) !== "\\") break;
    slashCount += 1;
  }
  return slashCount % 2 === 1;
};

/** Remove TeX comments while preserving line boundaries and escaped `\%`. */
const stripComments = (source: string): string => {
  let result = "";
  let cursor = 0;
  while (cursor < source.length) {
    const character = source.charAt(cursor);
    if (character !== "%" || isEscapedAt(source, cursor)) {
      result += character;
      cursor += 1;
      continue;
    }

    while (
      cursor < source.length &&
      source.charAt(cursor) !== "\n" &&
      source.charAt(cursor) !== "\r"
    ) {
      cursor += 1;
    }
  }
  return result;
};

const readBalanced = (
  source: string,
  start: number,
  open: string,
  close: string,
): BalancedValue | null => {
  if (source.charAt(start) !== open) return null;
  let depth = 0;
  for (let cursor = start; cursor < source.length; cursor += 1) {
    if (isEscapedAt(source, cursor)) continue;
    const character = source.charAt(cursor);
    if (character === open) depth += 1;
    if (character !== close) continue;
    depth -= 1;
    if (depth === 0) {
      return { value: source.slice(start + 1, cursor), end: cursor + 1 };
    }
  }
  return null;
};

const skipWhitespace = (source: string, start: number): number => {
  let cursor = start;
  while (/\s/.test(source.charAt(cursor))) cursor += 1;
  return cursor;
};

const truncate = (value: string): string => {
  const characters = Array.from(value);
  if (characters.length <= MAX_SNIPPET_LENGTH) return value;

  const tentative = characters.slice(0, MAX_SNIPPET_LENGTH - 1).join("");
  const wordBoundary = tentative.lastIndexOf(" ");
  const shortened =
    wordBoundary >= Math.floor(MAX_SNIPPET_LENGTH * 0.6)
      ? tentative.slice(0, wordBoundary)
      : tentative;
  return `${shortened.trimEnd()}…`;
};

/**
 * A deliberately small text projection, not a TeX interpreter. It unwraps a
 * handful of common text commands and drops every remaining command name.
 */
const toPlainText = (value: string): string => {
  let text = value;

  // Two/three-argument wrappers whose final/visible argument is useful.
  for (let pass = 0; pass < 6; pass += 1) {
    const previous = text;
    text = text
      .replace(/\\href\s*\{[^{}]*\}\s*\{([^{}]*)\}/g, "$1")
      .replace(
        /\\(?:textcolor|colorbox|foreignlanguage)\s*\{[^{}]*\}\s*\{([^{}]*)\}/g,
        "$1",
      )
      .replace(
        /\\(?:multicolumn|multirow)\s*\{[^{}]*\}\s*\{[^{}]*\}\s*\{([^{}]*)\}/g,
        "$1",
      )
      .replace(/\\texorpdfstring\s*\{([^{}]*)\}\s*\{[^{}]*\}/g, "$1")
      .replace(TEXT_WRAPPERS, "$1");
    if (text === previous) break;
  }

  text = text
    .replace(
      /\\(?:label|cite|citep|citet|ref|pageref|index)\*?\s*\{[^{}]*\}/g,
      " ",
    )
    .replace(/\\rule(?:\s*\[[^\]]*\])?\s*\{[^{}]*\}\s*\{[^{}]*\}/g, " ")
    .replace(/\\(?:begin|end)\s*\{[^{}]*\}/g, " ")
    .replace(/\\(?:ldots|dots)\b\s*(?:\{\})?/g, "…")
    .replace(/\\textemdash\b/g, "—")
    .replace(/\\textendash\b/g, "–")
    .replace(/\\([%&#_${}])/g, "$1")
    .replace(/\\\\(?:\[[^\]]*\])?/g, " ")
    .replace(/\\[A-Za-z@]+\*?(?:\s*\[[^\]]*\])?/g, " ")
    .replace(/\\[- ,;:!]/g, " ")
    .replace(/~/g, " ")
    .replace(/[{}$]/g, "")
    .replace(/\s+/g, " ")
    .trim();

  return truncate(text);
};

const isPrintable = (value: string): boolean =>
  value.length >= 3 && (value.match(/[\p{L}\p{N}]/gu)?.length ?? 0) >= 2;

const hasUnescapedAmpersand = (value: string): boolean => {
  for (let cursor = 0; cursor < value.length; cursor += 1) {
    if (value.charAt(cursor) === "&" && !isEscapedAt(value, cursor))
      return true;
  }
  return false;
};

const collectHeadingCandidates = (
  source: string,
): { sectionCount: number; candidates: Candidate[] } => {
  const candidates: Candidate[] = [];
  const candidateKeys = new Set<string>();
  let sectionCount = 0;
  const commandPattern =
    /\\(part|chapter|section|subsection|subsubsection|paragraph|subparagraph|caption)\*?/g;

  for (const match of source.matchAll(commandPattern)) {
    const offset = match.index ?? 0;
    if (isEscapedAt(source, offset)) continue;
    const command = match[1] ?? "";
    if (SECTION_COMMANDS.has(command)) sectionCount += 1;

    let cursor = skipWhitespace(source, offset + match[0].length);
    if (source.charAt(cursor) === "[") {
      const optional = readBalanced(source, cursor, "[", "]");
      if (optional) cursor = skipWhitespace(source, optional.end);
    }
    const argument = readBalanced(source, cursor, "{", "}");
    if (!argument) continue;
    const text = toPlainText(argument.value);
    const key = text.toLocaleLowerCase();
    if (
      isPrintable(text) &&
      !candidateKeys.has(key) &&
      candidates.length < MAX_CANDIDATES
    ) {
      candidateKeys.add(key);
      candidates.push({ offset, priority: 0, text });
    }
  }

  return { sectionCount, candidates };
};

const countEnvironments = (
  source: string,
): { tableCount: number; listCount: number } => {
  const stack: string[] = [];
  let tableCount = 0;
  let listCount = 0;
  const environmentPattern = /\\(begin|end)\s*\{([^{}]+)\}/g;

  for (const match of source.matchAll(environmentPattern)) {
    const offset = match.index ?? 0;
    if (isEscapedAt(source, offset)) continue;
    const direction = match[1];
    const environment = (match[2] ?? "").trim();

    if (direction === "begin") {
      if (LIST_ENVIRONMENTS.has(environment)) listCount += 1;
      if (TABLE_ENVIRONMENTS.has(environment)) {
        const insideTable = stack.some(
          (entry) =>
            entry === "table" || entry === "table*" || entry === "longtable",
        );
        if (!insideTable) tableCount += 1;
      }
      stack.push(environment);
      continue;
    }

    const matching = stack.lastIndexOf(environment);
    if (matching >= 0) stack.splice(matching, 1);
  }

  return { tableCount, listCount };
};

const collectLineCandidates = (source: string): Candidate[] => {
  const candidates: Candidate[] = [];
  const candidateKeys = new Set<string>();
  const lines = source.split(/\r\n|\r|\n/);
  let offset = 0;

  for (const line of lines) {
    const trimmed = line.trim();
    const isExplicitHeading =
      /^\\(?:part|chapter|section|subsection|subsubsection|paragraph|subparagraph|caption)\*?\b/.test(
        trimmed,
      );
    if (
      trimmed.length > 0 &&
      !isExplicitHeading &&
      !SKIPPED_LINE_COMMANDS.test(trimmed) &&
      !hasUnescapedAmpersand(trimmed)
    ) {
      const text = toPlainText(trimmed);
      const key = text.toLocaleLowerCase();
      if (
        isPrintable(text) &&
        !candidateKeys.has(key) &&
        candidates.length < MAX_CANDIDATES
      ) {
        candidateKeys.add(key);
        candidates.push({ offset, priority: 1, text });
      }
    }
    offset += line.length + 1;
  }

  return candidates;
};

const selectSnippets = (candidates: Candidate[]): string[] => {
  const selected: string[] = [];
  const seen = new Set<string>();

  candidates
    .sort(
      (left, right) =>
        left.offset - right.offset || left.priority - right.priority,
    )
    .some(({ text }) => {
      const key = text.toLocaleLowerCase();
      if (!seen.has(key)) {
        seen.add(key);
        selected.push(text);
      }
      return selected.length >= MAX_SNIPPETS;
    });

  return selected;
};

/**
 * Build a small, safe summary for an otherwise unknown direct `\\input`.
 * The parser never expands macros or executes TeX and returns plain strings.
 */
export const parseGenericInputPreview = (
  source: string | undefined,
): GenericInputPreview => {
  if (typeof source !== "string" || source.length === 0) return emptyPreview();

  const lineCount = countLines(source);
  try {
    const printableSource = stripComments(source).replace(/\r\n?/g, "\n");
    const headings = collectHeadingCandidates(printableSource);
    const environments = countEnvironments(printableSource);
    return {
      lineCount,
      sectionCount: headings.sectionCount,
      tableCount: environments.tableCount,
      listCount: environments.listCount,
      snippets: selectSnippets([
        ...headings.candidates,
        ...collectLineCandidates(printableSource),
      ]),
    };
  } catch {
    return emptyPreview(lineCount);
  }
};
