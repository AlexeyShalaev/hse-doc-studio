const DEFAULT_CAPTION = "Требования к функциональным характеристикам системы";

export type RequirementsTableHeaders = readonly [
  number: string,
  userStory: string,
  requirement: string,
  area: string,
];

const DEFAULT_HEADERS: RequirementsTableHeaders = [
  "№",
  "Пользовательская история",
  "Требование",
  "Область",
];

export type RequirementsTableRow = {
  id: string;
  userStory: string;
  requirement: string;
  area: string;
};

export type RequirementsTablePreview = {
  caption: string;
  headers: RequirementsTableHeaders;
  rows: RequirementsTableRow[];
};

type Group = { content: string; end: number };
type Command = { name: string; from: number; end: number };
type Environment = { body: string };

const fallbackPreview = (): RequirementsTablePreview => ({
  caption: DEFAULT_CAPTION,
  headers: [...DEFAULT_HEADERS],
  rows: [],
});

const isControlWordCharacter = (character: string): boolean =>
  /[A-Za-z@]/.test(character);

/** Remove TeX comments while preserving escaped percent signs and newlines. */
const removeComments = (source: string): string => {
  let output = "";

  for (let cursor = 0; cursor < source.length; cursor += 1) {
    const character = source.charAt(cursor);
    if (character === "\\") {
      output += character;
      if (cursor + 1 < source.length) {
        cursor += 1;
        output += source.charAt(cursor);
      }
      continue;
    }
    if (character !== "%") {
      output += character;
      continue;
    }

    while (cursor < source.length && source.charAt(cursor) !== "\n") {
      cursor += 1;
    }
    if (cursor < source.length) output += "\n";
  }

  return output;
};

const skipWhitespace = (source: string, from: number): number => {
  let cursor = from;
  while (cursor < source.length && /\s/.test(source.charAt(cursor))) {
    cursor += 1;
  }
  return cursor;
};

const readGroup = (
  source: string,
  from: number,
  opening = "{",
  closing = "}",
): Group | undefined => {
  if (source.charAt(from) !== opening) return undefined;

  let depth = 1;
  for (let cursor = from + 1; cursor < source.length; cursor += 1) {
    const character = source.charAt(cursor);
    if (character === "\\") {
      cursor += 1;
      continue;
    }
    if (character === opening) {
      depth += 1;
      continue;
    }
    if (character !== closing) continue;

    depth -= 1;
    if (depth === 0) {
      return {
        content: source.slice(from + 1, cursor),
        end: cursor + 1,
      };
    }
  }

  return undefined;
};

const readControlWord = (source: string, from: number): Command | undefined => {
  if (source.charAt(from) !== "\\") return undefined;

  let end = from + 1;
  while (end < source.length && isControlWordCharacter(source.charAt(end))) {
    end += 1;
  }
  if (end === from + 1) return undefined;

  return { name: source.slice(from + 1, end), from, end };
};

const findCommand = (
  source: string,
  name: string,
  from = 0,
): Command | undefined => {
  for (let cursor = from; cursor < source.length; cursor += 1) {
    if (source.charAt(cursor) !== "\\") continue;
    const command = readControlWord(source, cursor);
    if (!command) {
      cursor += 1;
      continue;
    }
    if (command.name === name) return command;
    cursor = command.end - 1;
  }
  return undefined;
};

const TABLE_ENVIRONMENTS = new Set([
  "longtable",
  "xltabular",
  "tabularx",
  "tabular",
]);

const tableBodyStart = (
  source: string,
  environmentName: string,
  from: number,
): number | undefined => {
  let cursor = skipWhitespace(source, from);
  if (source.charAt(cursor) === "[") {
    const position = readGroup(source, cursor, "[", "]");
    if (!position) return undefined;
    cursor = skipWhitespace(source, position.end);
  }

  // tabularx/xltabular take width + column specification; longtable/tabular
  // take only the column specification.
  const argumentCount =
    environmentName === "tabularx" || environmentName === "xltabular" ? 2 : 1;
  for (let index = 0; index < argumentCount; index += 1) {
    const argument = readGroup(source, cursor);
    if (!argument) return undefined;
    cursor = skipWhitespace(source, argument.end);
  }
  return cursor;
};

const findTableEnvironment = (source: string): Environment | undefined => {
  let searchFrom = 0;

  while (searchFrom < source.length) {
    const begin = findCommand(source, "begin", searchFrom);
    if (!begin) return undefined;
    const nameStart = skipWhitespace(source, begin.end);
    const nameGroup = readGroup(source, nameStart);
    if (!nameGroup) {
      searchFrom = begin.end;
      continue;
    }
    const environmentName = nameGroup.content.trim();
    if (!TABLE_ENVIRONMENTS.has(environmentName)) {
      searchFrom = nameGroup.end;
      continue;
    }
    const bodyStart = tableBodyStart(source, environmentName, nameGroup.end);
    if (bodyStart === undefined) {
      searchFrom = nameGroup.end;
      continue;
    }

    let nesting = 1;
    let cursor = bodyStart;
    while (cursor < source.length) {
      const nextBegin = findCommand(source, "begin", cursor);
      const nextEnd = findCommand(source, "end", cursor);
      const next =
        nextBegin && (!nextEnd || nextBegin.from < nextEnd.from)
          ? nextBegin
          : nextEnd;
      if (!next) return undefined;

      const nextNameStart = skipWhitespace(source, next.end);
      const nextName = readGroup(source, nextNameStart);
      if (!nextName) {
        cursor = next.end;
        continue;
      }
      if (nextName.content.trim() === environmentName) {
        nesting += next.name === "begin" ? 1 : -1;
        if (nesting === 0) {
          return { body: source.slice(bodyStart, next.from) };
        }
      }
      cursor = nextName.end;
    }
    return undefined;
  }

  return undefined;
};

const ONE_ARGUMENT_TEXT_COMMANDS = new Set([
  "textbf",
  "textit",
  "emph",
  "underline",
  "textrm",
  "textsf",
  "texttt",
  "makecell",
  "mbox",
]);

const SPACE_COMMANDS = new Set([
  "quad",
  "qquad",
  "enspace",
  "enskip",
  "thinspace",
]);

const readRequiredArgument = (
  source: string,
  from: number,
): Group | undefined => readGroup(source, skipWhitespace(source, from));

const renderLatexText = (source: string): string => {
  let output = "";

  for (let cursor = 0; cursor < source.length; cursor += 1) {
    const character = source.charAt(cursor);
    if (character === "~") {
      output += " ";
      continue;
    }
    if (character === "{") {
      const group = readGroup(source, cursor);
      if (group) {
        output += renderLatexText(group.content);
        cursor = group.end - 1;
      }
      continue;
    }
    if (character === "}") continue;
    if (character !== "\\") {
      output += character;
      continue;
    }

    const escaped = source.charAt(cursor + 1);
    if ("%&#_$ {}".includes(escaped)) {
      output += escaped === " " ? " " : escaped;
      cursor += 1;
      continue;
    }
    if (escaped === "\\") {
      output += " ";
      cursor += 1;
      continue;
    }

    const command = readControlWord(source, cursor);
    if (!command) continue;
    cursor = command.end - 1;

    if (command.name === "ldots" || command.name === "dots") {
      output += "…";
      continue;
    }
    if (command.name === "textendash") {
      output += "–";
      continue;
    }
    if (command.name === "textemdash") {
      output += "—";
      continue;
    }
    if (SPACE_COMMANDS.has(command.name)) {
      output += " ";
      continue;
    }

    if (command.name === "req") {
      const id = readRequiredArgument(source, command.end);
      const text = id ? readRequiredArgument(source, id.end) : undefined;
      if (text) {
        output += renderLatexText(text.content);
        cursor = text.end - 1;
      }
      continue;
    }

    if (ONE_ARGUMENT_TEXT_COMMANDS.has(command.name)) {
      const argument = readRequiredArgument(source, command.end);
      if (argument) {
        output += renderLatexText(argument.content);
        cursor = argument.end - 1;
      }
      continue;
    }

    if (command.name === "multicolumn") {
      const count = readRequiredArgument(source, command.end);
      const format = count
        ? readRequiredArgument(source, count.end)
        : undefined;
      const text = format
        ? readRequiredArgument(source, format.end)
        : undefined;
      if (text) {
        output += renderLatexText(text.content);
        cursor = text.end - 1;
      }
      continue;
    }

    // Unknown commands remain harmless: their control word is omitted, while
    // any following groups are visited normally and keep their printable text.
  }

  return output.replace(/\s+/g, " ").trim();
};

/** Split table source by top-level cell and row separators. */
const splitTableRows = (source: string): string[][] => {
  const rows: string[][] = [];
  let cells: string[] = [];
  let cell = "";
  let braceDepth = 0;
  let cursor = 0;

  const finishRow = (): void => {
    cells.push(cell);
    rows.push(cells);
    cells = [];
    cell = "";
  };

  while (cursor < source.length) {
    const character = source.charAt(cursor);

    if (character === "\\") {
      const next = source.charAt(cursor + 1);
      if (next === "\\" && braceDepth === 0) {
        finishRow();
        cursor += 2;
        cursor = skipWhitespace(source, cursor);
        if (source.charAt(cursor) === "[") {
          const spacing = readGroup(source, cursor, "[", "]");
          if (spacing) cursor = spacing.end;
        }
        continue;
      }
      if ("%&#_${}".includes(next)) {
        cell += character + next;
        cursor += 2;
        continue;
      }
      cell += character;
      cursor += 1;
      continue;
    }

    if (character === "{") braceDepth += 1;
    if (character === "}" && braceDepth > 0) braceDepth -= 1;
    if (character === "&" && braceDepth === 0) {
      cells.push(cell);
      cell = "";
      cursor += 1;
      continue;
    }

    cell += character;
    cursor += 1;
  }

  if (cell.trim() !== "" || cells.length > 0) finishRow();
  return rows;
};

const renderedCells = (row: readonly string[]): string[] =>
  row.map((cell) => renderLatexText(cell));

const sameCells = (
  left: readonly string[],
  right: readonly string[],
): boolean =>
  left.length === right.length &&
  left.every((cell, index) => cell === right[index]);

const looksLikeHeader = (
  raw: readonly string[],
  rendered: readonly string[],
): boolean =>
  raw.filter((cell) => /\\textbf\s*\{/.test(cell)).length >= 3 ||
  (rendered[0] === "№" && rendered.includes("Требование"));

const extractHeaders = (body: string): RequirementsTableHeaders => {
  const firstHead = findCommand(body, "endfirsthead");
  const candidateSource = firstHead ? body.slice(0, firstHead.from) : body;
  const candidates = splitTableRows(candidateSource);

  for (let index = candidates.length - 1; index >= 0; index -= 1) {
    const candidate = candidates[index];
    if (candidate?.length !== 4) continue;
    const rendered = renderedCells(candidate);
    if (!looksLikeHeader(candidate, rendered)) continue;
    return [
      rendered[0] === ""
        ? DEFAULT_HEADERS[0]
        : (rendered[0] ?? DEFAULT_HEADERS[0]),
      rendered[1] === ""
        ? DEFAULT_HEADERS[1]
        : (rendered[1] ?? DEFAULT_HEADERS[1]),
      rendered[2] === ""
        ? DEFAULT_HEADERS[2]
        : (rendered[2] ?? DEFAULT_HEADERS[2]),
      rendered[3] === ""
        ? DEFAULT_HEADERS[3]
        : (rendered[3] ?? DEFAULT_HEADERS[3]),
    ];
  }

  return [...DEFAULT_HEADERS];
};

const extractCaption = (body: string): string => {
  const command = findCommand(body, "caption");
  if (!command) return DEFAULT_CAPTION;

  let argumentStart = skipWhitespace(body, command.end);
  if (body.charAt(argumentStart) === "[") {
    const short = readGroup(body, argumentStart, "[", "]");
    if (!short) return DEFAULT_CAPTION;
    argumentStart = skipWhitespace(body, short.end);
  }
  const caption = readGroup(body, argumentStart);
  if (!caption) return DEFAULT_CAPTION;

  const rendered = renderLatexText(caption.content);
  return rendered === "" ? DEFAULT_CAPTION : rendered;
};

const extractReqId = (source: string): string => {
  const command = findCommand(source, "req");
  if (!command) return "";
  const id = readRequiredArgument(source, command.end);
  return id ? renderLatexText(id.content) : "";
};

const extractRows = (
  body: string,
  headers: RequirementsTableHeaders,
): RequirementsTableRow[] => {
  const lastFoot = findCommand(body, "endlastfoot");
  const rowSource = lastFoot ? body.slice(lastFoot.end) : body;
  const rows: RequirementsTableRow[] = [];

  for (const rawRow of splitTableRows(rowSource)) {
    if (rawRow.length !== 4) continue;
    const cells = renderedCells(rawRow);
    if (sameCells(cells, headers) || looksLikeHeader(rawRow, cells)) continue;
    if (cells.every((cell) => cell === "")) continue;

    const requirementId = extractReqId(rawRow[2] ?? "");
    const visibleId = cells[0] ?? "";
    const id = visibleId === "" ? requirementId : visibleId;
    if (id === "") continue;

    rows.push({
      id,
      userStory: cells[1] ?? "",
      requirement: cells[2] ?? "",
      area: cells[3] ?? "",
    });
  }

  return rows;
};

/**
 * Parse the source-backed functional-requirements table into a small semantic
 * model. This intentionally interprets only the table's printable content;
 * arbitrary TeX execution and exact PDF geometry remain out of scope.
 */
export const parseRequirementsTablePreview = (
  source: string | undefined,
): RequirementsTablePreview => {
  if (!source) return fallbackPreview();

  const withoutComments = removeComments(source);
  const environment = findTableEnvironment(withoutComments);
  if (!environment) return fallbackPreview();

  const headers = extractHeaders(environment.body);
  return {
    caption: extractCaption(environment.body),
    headers,
    rows: extractRows(environment.body, headers),
  };
};
