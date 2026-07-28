export type HeadingAlignment = "left" | "center" | "right";

const HEADING_LEVELS: Readonly<Record<string, number>> = {
  chapter: 1,
  section: 2,
  subsection: 3,
  subsubsection: 4,
  paragraph: 5,
  subparagraph: 5,
};

type ParsedGroup = {
  content: string;
  end: number;
};

const isControlWordCharacter = (character: string): boolean =>
  /[A-Za-z@]/.test(character);

const skipTrivia = (source: string, from: number): number => {
  let cursor = from;

  while (cursor < source.length) {
    const character = source.charAt(cursor);
    if (/\s/.test(character)) {
      cursor += 1;
      continue;
    }
    if (character !== "%") break;

    while (cursor < source.length && source.charAt(cursor) !== "\n") {
      cursor += 1;
    }
  }

  return cursor;
};

/** Read a brace or bracket group while ignoring escaped delimiters/comments. */
const readGroup = (
  source: string,
  from: number,
  opening: "{" | "[",
  closing: "}" | "]",
): ParsedGroup | undefined => {
  if (source.charAt(from) !== opening) return undefined;

  let delimiterDepth = 1;
  let braceDepth = 0;

  for (let cursor = from + 1; cursor < source.length; cursor += 1) {
    const character = source.charAt(cursor);

    if (character === "\\") {
      // A control symbol such as \{ or \] cannot close the current group.
      // For control words it is still safe to skip the first letter: braces
      // following the word are visited on subsequent iterations.
      cursor += 1;
      continue;
    }

    if (character === "%") {
      while (cursor < source.length && source.charAt(cursor) !== "\n") {
        cursor += 1;
      }
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
      delimiterDepth += 1;
      continue;
    }
    if (character !== closing) continue;

    delimiterDepth -= 1;
    if (delimiterDepth === 0) {
      return {
        content: source.slice(from + 1, cursor),
        end: cursor + 1,
      };
    }
  }

  return undefined;
};

const readControlWord = (
  source: string,
  from: number,
): { name: string; end: number } | undefined => {
  if (source.charAt(from) !== "\\") return undefined;

  let end = from + 1;
  while (end < source.length && isControlWordCharacter(source.charAt(end))) {
    end += 1;
  }
  if (end === from + 1) return undefined;

  return { name: source.slice(from + 1, end), end };
};

const headingLevelFromGroup = (content: string): number | undefined => {
  const start = skipTrivia(content, 0);
  const command = readControlWord(content, start);
  if (!command || skipTrivia(content, command.end) !== content.length) {
    return undefined;
  }

  return HEADING_LEVELS[command.name];
};

const alignmentFromFormat = (format: string): HeadingAlignment | undefined => {
  let alignment: HeadingAlignment | undefined;

  for (let cursor = 0; cursor < format.length; cursor += 1) {
    const character = format.charAt(cursor);
    if (character === "%") {
      while (cursor < format.length && format.charAt(cursor) !== "\n") {
        cursor += 1;
      }
      continue;
    }
    if (character !== "\\") continue;

    const command = readControlWord(format, cursor);
    if (!command) {
      cursor += 1;
      continue;
    }
    cursor = command.end - 1;

    if (command.name === "centering") alignment = "center";
    if (command.name === "raggedleft") alignment = "right";
    if (command.name === "raggedright") alignment = "left";
  }

  return alignment;
};

/**
 * Extract effective explicit heading alignments from `titlesec` declarations.
 *
 * `\titleformat{\section}[shape]{format}{label}{sep}{before}` stores its
 * alignment in the `format` group. Repeated declarations follow TeX's normal
 * last-one-wins behaviour. A declaration without an explicit alignment clears
 * an alignment extracted from an earlier declaration for the same level.
 */
export const parseHeadingStyles = (
  source: string,
): Partial<Record<number, HeadingAlignment>> => {
  const styles: Partial<Record<number, HeadingAlignment>> = {};

  for (let cursor = 0; cursor < source.length; cursor += 1) {
    const character = source.charAt(cursor);
    if (character === "%") {
      while (cursor < source.length && source.charAt(cursor) !== "\n") {
        cursor += 1;
      }
      continue;
    }
    if (character !== "\\") continue;

    const command = readControlWord(source, cursor);
    if (!command) {
      cursor += 1;
      continue;
    }
    if (command.name !== "titleformat") {
      cursor = command.end - 1;
      continue;
    }

    let argumentStart = skipTrivia(source, command.end);
    const headingGroup = readGroup(source, argumentStart, "{", "}");
    if (!headingGroup) continue;

    const level = headingLevelFromGroup(headingGroup.content);
    argumentStart = skipTrivia(source, headingGroup.end);

    if (source.charAt(argumentStart) === "[") {
      const shapeGroup = readGroup(source, argumentStart, "[", "]");
      if (!shapeGroup) continue;
      argumentStart = skipTrivia(source, shapeGroup.end);
    }

    const formatGroup = readGroup(source, argumentStart, "{", "}");
    if (!formatGroup) continue;
    cursor = formatGroup.end - 1;
    if (level === undefined) continue;

    const alignment = alignmentFromFormat(formatGroup.content);
    if (alignment === undefined) {
      Reflect.deleteProperty(styles, level);
    } else {
      styles[level] = alignment;
    }
  }

  return styles;
};

/** Direct `\\input` / `\\include` targets, in TeX order. */
export const findLatexInputTargets = (source: string): string[] => {
  const paths: string[] = [];
  const seen = new Set<string>();

  for (let cursor = 0; cursor < source.length; cursor += 1) {
    const character = source.charAt(cursor);
    if (character === "%") {
      while (cursor < source.length && source.charAt(cursor) !== "\n") {
        cursor += 1;
      }
      continue;
    }
    if (character !== "\\") continue;

    const command = readControlWord(source, cursor);
    if (!command) continue;
    cursor = command.end - 1;
    if (
      command.name !== "input" &&
      command.name !== "include" &&
      command.name !== "subfile"
    ) {
      continue;
    }

    const argumentStart = skipTrivia(source, command.end);
    const argument = readGroup(source, argumentStart, "{", "}");
    let path = "";
    if (argument) {
      cursor = argument.end - 1;
      path = argument.content.trim();
    } else {
      // TeX also accepts `\input chapter.tex`. Dynamic control-sequence
      // targets remain unresolved deliberately; only a literal token is safe.
      if (source.charAt(argumentStart) === "\\") continue;
      let argumentEnd = argumentStart;
      while (
        argumentEnd < source.length &&
        !/[\s%{}]/.test(source.charAt(argumentEnd))
      ) {
        argumentEnd += 1;
      }
      path = source.slice(argumentStart, argumentEnd).trim();
      cursor = Math.max(cursor, argumentEnd - 1);
    }
    if (path !== "" && !seen.has(path)) {
      seen.add(path);
      paths.push(path);
    }
  }

  return paths;
};

/**
 * Directly included style-profile files, in TeX order. The host resolves these
 * against the open document and loads only what that document actually uses.
 */
export const findHeadingStyleInputs = (source: string): string[] =>
  findLatexInputTargets(source).filter((path) => {
    const basename = (path.replace(/\\/g, "/").split("/").pop() ?? path)
      .replace(/\.tex$/i, "")
      .toLocaleLowerCase();
    return basename === "preamble" || basename === "styles";
  });
