const MAX_CAPTION_CHARS = 240;
const MAX_PATH_CHARS = 400;

export type FigurePreview = {
  /** First `\includegraphics{…}` path exactly as written, or null. */
  image: string | null;
  /** Rendered `\caption{…}` text, or null. */
  caption: string | null;
};

type Group = { content: string; end: number };
type Command = { name: string; from: number; end: number };

const EMPTY_PREVIEW: FigurePreview = { image: null, caption: null };

const isControlWordCharacter = (character: string): boolean =>
  /[A-Za-z@]/.test(character);

/** Drop TeX comments while preserving escaped percent signs and newlines. */
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
      return { content: source.slice(from + 1, cursor), end: cursor + 1 };
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
  "mbox",
  "MakeUppercase",
  "MakeLowercase",
]);

const SYMBOL: Record<string, string> = {
  ldots: "…",
  dots: "…",
  textendash: "–",
  textemdash: "—",
};

/** A small printable projection of caption LaTeX — never executed as TeX. */
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
      output += escaped;
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

    const glyph = SYMBOL[command.name];
    if (glyph !== undefined) {
      output += glyph;
      continue;
    }
    if (command.name === "label" || command.name === "ref") {
      const argument = readRequiredArgument(source, command.end);
      if (argument) cursor = argument.end - 1;
      continue;
    }
    if (ONE_ARGUMENT_WRAPPERS.has(command.name)) {
      const argument = readRequiredArgument(source, command.end);
      if (argument) {
        output += renderLatexText(argument.content);
        cursor = argument.end - 1;
      }
      continue;
    }

    // Unknown commands drop their control word; following groups are visited
    // normally and keep their printable text.
  }

  return output.replace(/\s+/g, " ").trim();
};

const extractImage = (source: string): string | null => {
  const command = findCommand(source, "includegraphics");
  if (!command) return null;

  let cursor = skipWhitespace(source, command.end);
  if (source.charAt(cursor) === "[") {
    const options = readGroup(source, cursor, "[", "]");
    if (!options) return null;
    cursor = skipWhitespace(source, options.end);
  }
  const path = readGroup(source, cursor);
  if (!path) return null;
  const value = path.content.trim();
  return value === "" ? null : value.slice(0, MAX_PATH_CHARS);
};

const extractCaption = (source: string): string | null => {
  const command = findCommand(source, "caption");
  if (!command) return null;

  let cursor = skipWhitespace(source, command.end);
  if (source.charAt(cursor) === "[") {
    const short = readGroup(source, cursor, "[", "]");
    if (!short) return null;
    cursor = skipWhitespace(source, short.end);
  }
  const caption = readGroup(source, cursor);
  if (!caption) return null;
  const rendered = renderLatexText(caption.content);
  return rendered === "" ? null : rendered.slice(0, MAX_CAPTION_CHARS);
};

/**
 * Parse a `figure` environment into its printable essentials: the first
 * embedded image path and the rendered caption. Only the caption's printable
 * projection is interpreted; arbitrary TeX execution stays out of scope.
 */
export const parseFigurePreview = (
  source: string | undefined,
): FigurePreview => {
  if (!source) return { ...EMPTY_PREVIEW };
  const withoutComments = removeComments(source);
  return {
    image: extractImage(withoutComments),
    caption: extractCaption(withoutComments),
  };
};
