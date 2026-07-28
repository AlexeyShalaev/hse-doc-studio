const MAX_COLUMNS = 12;
const MAX_ROWS = 100;
const MAX_CELL_CHARS = 300;
const MAX_RAW_CELL_CHARS = 2_400;
const MAX_SCANNED_ROWS = MAX_ROWS + 32;
const MAX_RENDER_CHARS = MAX_CELL_CHARS * 4;

export type TablePreview = {
  caption: string | null;
  headers: string[];
  rows: string[][];
};

type Group = { content: string; end: number };
type Command = { name: string; from: number; end: number };
type TableEnvironment = { body: string; name: string };
type ParsedRow = { raw: string[]; cells: string[] };

const EMPTY_PREVIEW: TablePreview = { caption: null, headers: [], rows: [] };

const isControlWordCharacter = (character: string): boolean =>
  /[A-Za-z@]/.test(character);

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
  let braceDepth = 0;
  for (let cursor = from + 1; cursor < source.length; cursor += 1) {
    const character = source.charAt(cursor);
    if (character === "\\") {
      cursor += 1;
      continue;
    }
    if (opening === "[" && character === "{") {
      braceDepth += 1;
      continue;
    }
    if (opening === "[" && character === "}" && braceDepth > 0) {
      braceDepth -= 1;
      continue;
    }
    if (opening === "[" && braceDepth > 0) continue;
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
  "tabular",
  "tabularx",
  "xltabular",
  "longtable",
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

  const argumentCount =
    environmentName === "tabularx" || environmentName === "xltabular" ? 2 : 1;
  for (let index = 0; index < argumentCount; index += 1) {
    const argument = readGroup(source, cursor);
    if (!argument) return undefined;
    cursor = skipWhitespace(source, argument.end);
  }
  return cursor;
};

const findTableEnvironment = (source: string): TableEnvironment | undefined => {
  let searchFrom = 0;

  while (searchFrom < source.length) {
    const begin = findCommand(source, "begin", searchFrom);
    if (!begin) return undefined;
    const nameGroup = readGroup(source, skipWhitespace(source, begin.end));
    if (!nameGroup) {
      searchFrom = begin.end;
      continue;
    }
    const name = nameGroup.content.trim();
    if (!TABLE_ENVIRONMENTS.has(name)) {
      searchFrom = nameGroup.end;
      continue;
    }

    const bodyStart = tableBodyStart(source, name, nameGroup.end);
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

      const nextName = readGroup(source, skipWhitespace(source, next.end));
      if (!nextName) {
        cursor = next.end;
        continue;
      }
      if (nextName.content.trim() === name) {
        nesting += next.name === "begin" ? 1 : -1;
        if (nesting === 0) {
          return { body: source.slice(bodyStart, next.from), name };
        }
      }
      cursor = nextName.end;
    }
    return undefined;
  }

  return undefined;
};

const readRequiredArgument = (
  source: string,
  from: number,
): Group | undefined => readGroup(source, skipWhitespace(source, from));

const ONE_ARGUMENT_WRAPPERS = new Set([
  "textbf",
  "textit",
  "emph",
  "underline",
  "textrm",
  "textsf",
  "texttt",
  "textnormal",
  "makecell",
  "shortstack",
  "mbox",
]);

const SPACE_COMMANDS = new Set([
  "newline",
  "quad",
  "qquad",
  "enspace",
  "enskip",
  "thinspace",
]);

const NO_TEXT_ONE_ARGUMENT_COMMANDS = new Set([
  "cline",
  "cmidrule",
  "label",
  "cellcolor",
  "rowcolor",
  "color",
]);

const appendBounded = (output: string, addition: string): string =>
  output.length >= MAX_RENDER_CHARS
    ? output
    : (output + addition).slice(0, MAX_RENDER_CHARS);

const renderLatexText = (source: string): string => {
  let output = "";

  for (
    let cursor = 0;
    cursor < source.length && output.length < MAX_RENDER_CHARS;
    cursor += 1
  ) {
    const character = source.charAt(cursor);
    if (character === "~") {
      output = appendBounded(output, " ");
      continue;
    }
    if (character === "{") {
      const group = readGroup(source, cursor);
      if (group) {
        output = appendBounded(output, renderLatexText(group.content));
        cursor = group.end - 1;
      }
      continue;
    }
    if (character === "}") continue;
    if (character !== "\\") {
      output = appendBounded(output, character);
      continue;
    }

    const escaped = source.charAt(cursor + 1);
    if ("%&#_$ {}".includes(escaped)) {
      output = appendBounded(output, escaped);
      cursor += 1;
      continue;
    }
    if (escaped === "\\") {
      output = appendBounded(output, " ");
      cursor += 1;
      continue;
    }

    const command = readControlWord(source, cursor);
    if (!command) continue;
    cursor = command.end - 1;

    const symbol: Record<string, string> = {
      cmpplus: "+",
      cmpminus: "−",
      cmpplanned: "±",
      ldots: "…",
      dots: "…",
      textendash: "–",
      textemdash: "—",
    };
    const glyph = symbol[command.name];
    if (glyph !== undefined) {
      output = appendBounded(output, glyph);
      continue;
    }
    if (SPACE_COMMANDS.has(command.name)) {
      output = appendBounded(output, " ");
      continue;
    }

    if (ONE_ARGUMENT_WRAPPERS.has(command.name)) {
      const argument = readRequiredArgument(source, command.end);
      if (argument) {
        output = appendBounded(output, renderLatexText(argument.content));
        cursor = argument.end - 1;
      }
      continue;
    }

    if (NO_TEXT_ONE_ARGUMENT_COMMANDS.has(command.name)) {
      const argument = readRequiredArgument(source, command.end);
      if (argument) cursor = argument.end - 1;
      continue;
    }

    if (command.name === "multicolumn" || command.name === "multirow") {
      const count = readRequiredArgument(source, command.end);
      const format = count
        ? readRequiredArgument(source, count.end)
        : undefined;
      const text = format
        ? readRequiredArgument(source, format.end)
        : undefined;
      if (text) {
        output = appendBounded(output, renderLatexText(text.content));
        cursor = text.end - 1;
      }
      continue;
    }

    if (command.name === "req") {
      const id = readRequiredArgument(source, command.end);
      const text = id ? readRequiredArgument(source, id.end) : undefined;
      if (text) {
        output = appendBounded(output, renderLatexText(text.content));
        cursor = text.end - 1;
      }
      continue;
    }

    // Declarations and unknown control words have no standalone printable
    // representation. Their following groups are still visited normally.
  }

  return output.replace(/\s+/g, " ").trim();
};

const limitCell = (value: string): string =>
  value.length <= MAX_CELL_CHARS
    ? value
    : value.slice(0, MAX_CELL_CHARS - 1) + "…";

const splitTableRows = (source: string): string[][] => {
  const rows: string[][] = [];
  let cells: string[] = [];
  let cell = "";
  let braceDepth = 0;
  let cursor = 0;

  const append = (value: string): void => {
    if (cell.length < MAX_RAW_CELL_CHARS) {
      cell += value.slice(0, MAX_RAW_CELL_CHARS - cell.length);
    }
  };
  const finishCell = (): void => {
    if (cells.length < MAX_COLUMNS) cells.push(cell);
    cell = "";
  };
  const finishRow = (): void => {
    finishCell();
    rows.push(cells);
    cells = [];
  };

  while (cursor < source.length && rows.length < MAX_SCANNED_ROWS) {
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
        append(character + next);
        cursor += 2;
        continue;
      }
      append(character);
      cursor += 1;
      continue;
    }

    if (character === "{") braceDepth += 1;
    if (character === "}" && braceDepth > 0) braceDepth -= 1;
    if (character === "&" && braceDepth === 0) {
      finishCell();
      cursor += 1;
      continue;
    }

    append(character);
    cursor += 1;
  }

  if (
    rows.length < MAX_SCANNED_ROWS &&
    (cell.trim() !== "" || cells.length > 0)
  ) {
    finishRow();
  }
  return rows;
};

const CONTROL_ROW_COMMANDS = [
  "caption",
  "label",
  "endfirsthead",
  "endhead",
  "endfoot",
  "endlastfoot",
] as const;

const isControlRow = (raw: readonly string[]): boolean => {
  const source = raw.join("&");
  return CONTROL_ROW_COMMANDS.some((name) => findCommand(source, name));
};

const parseRows = (source: string): ParsedRow[] => {
  const rows: ParsedRow[] = [];
  for (const raw of splitTableRows(source)) {
    if (isControlRow(raw)) continue;
    const cells = raw.map((cell) => limitCell(renderLatexText(cell)));
    if (cells.every((cell) => cell === "")) continue;
    rows.push({ raw, cells });
  }
  return rows;
};

const isBoldHeavy = (row: ParsedRow): boolean => {
  if (row.cells.length < 2) return false;
  const nonEmpty = row.cells.filter((cell) => cell !== "").length;
  if (nonEmpty < 2) return false;
  const bold = row.raw.filter((cell) =>
    /\\(?:textbf\s*\{|bfseries\b)/.test(cell),
  ).length;
  return bold >= Math.ceil(nonEmpty / 2);
};

const sameCells = (
  left: readonly string[],
  right: readonly string[],
): boolean =>
  left.length === right.length &&
  left.every((cell, index) => cell === right[index]);

const extractCaption = (source: string): string | null => {
  const command = findCommand(source, "caption");
  if (!command) return null;

  let argumentStart = skipWhitespace(source, command.end);
  if (source.charAt(argumentStart) === "[") {
    const short = readGroup(source, argumentStart, "[", "]");
    if (!short) return null;
    argumentStart = skipWhitespace(source, short.end);
  }
  const caption = readGroup(source, argumentStart);
  if (!caption) return null;
  const rendered = limitCell(renderLatexText(caption.content));
  return rendered === "" ? null : rendered;
};

/**
 * Parse the first supported LaTeX table into a bounded semantic preview.
 * Unsupported layout commands are omitted; their printable argument content
 * is retained wherever it can be interpreted safely.
 */
export const parseTablePreview = (source: string | undefined): TablePreview => {
  if (!source) return { ...EMPTY_PREVIEW };

  const withoutComments = removeComments(source);
  const environment = findTableEnvironment(withoutComments);
  if (!environment) return { ...EMPTY_PREVIEW };

  const firstHead =
    environment.name === "longtable"
      ? findCommand(environment.body, "endfirsthead")
      : undefined;
  const lastFoot =
    environment.name === "longtable"
      ? findCommand(environment.body, "endlastfoot")
      : undefined;

  const headerCandidates = parseRows(
    firstHead ? environment.body.slice(0, firstHead.from) : environment.body,
  );
  const header = headerCandidates.find(isBoldHeavy);
  const dataRows = parseRows(
    lastFoot ? environment.body.slice(lastFoot.end) : environment.body,
  );

  const rows = dataRows
    .filter(
      (row) =>
        !header || !isBoldHeavy(row) || !sameCells(row.cells, header.cells),
    )
    .slice(0, MAX_ROWS)
    .map((row) => row.cells.slice(0, MAX_COLUMNS));

  return {
    caption: extractCaption(withoutComments),
    headers: header?.cells.slice(0, MAX_COLUMNS) ?? [],
    rows,
  };
};
