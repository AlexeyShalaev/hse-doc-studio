const MAX_SOURCE_LENGTH = 256_000;
const MAX_OPTIONS_LENGTH = 16_000;
const MAX_CODE_LENGTH = 32_000;
const MAX_CODE_LINES = 500;
const MAX_CAPTION_LENGTH = 240;
const MAX_IDENTIFIER_LENGTH = 160;

const TEXT_WRAPPERS =
  /\\(?:textbf|textit|emph|underline|textrm|textsf|texttt|textsc|mbox|makecell|MakeUppercase|MakeLowercase)\*?\s*\{([^{}]*)\}/g;

export type ListingPreview = {
  language: string;
  caption: string;
  label: string;
  /** Exact, inert environment body. It is never interpreted as TeX or HTML. */
  code: string;
  complete: boolean;
  truncated: boolean;
};

type BalancedRange = {
  end: number;
};

type ListingOptions = {
  language: string;
  caption: string;
  label: string;
  truncated: boolean;
};

const emptyPreview = (truncated = false): ListingPreview => ({
  language: "",
  caption: "",
  label: "",
  code: "",
  complete: false,
  truncated,
});

const isEscapedAt = (source: string, index: number): boolean => {
  let slashCount = 0;
  for (let cursor = index - 1; cursor >= 0; cursor -= 1) {
    if (source.charAt(cursor) !== "\\") break;
    slashCount += 1;
  }
  return slashCount % 2 === 1;
};

/** Replace comments with spaces so all structural offsets remain stable. */
const maskComments = (source: string): string => {
  const result: string[] = [];
  let insideComment = false;

  for (let cursor = 0; cursor < source.length; cursor += 1) {
    const character = source.charAt(cursor);
    if (insideComment && character !== "\n" && character !== "\r") {
      result.push(" ");
      continue;
    }
    if (insideComment) insideComment = false;
    if (character === "%" && !isEscapedAt(source, cursor)) {
      insideComment = true;
      result.push(" ");
      continue;
    }
    result.push(character);
  }

  return result.join("");
};

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
): BalancedRange | null => {
  if (source.charAt(start) !== open) return null;
  let depth = 0;

  for (let cursor = start; cursor < source.length; cursor += 1) {
    if (isEscapedAt(source, cursor)) continue;
    const character = source.charAt(cursor);
    if (character === open) depth += 1;
    if (character !== close) continue;
    depth -= 1;
    if (depth === 0) return { end: cursor + 1 };
  }

  return null;
};

const skipWhitespace = (source: string, start: number): number => {
  let cursor = start;
  while (cursor < source.length && /\s/.test(source.charAt(cursor))) {
    cursor += 1;
  }
  return cursor;
};

const truncateCharacters = (value: string, limit: number): string => {
  const characters = Array.from(value);
  if (characters.length <= limit) return value;
  return characters.slice(0, limit).join("");
};

const trimOuterBraces = (value: string): string => {
  let result = value.trim();

  for (let pass = 0; pass < 6 && result.startsWith("{"); pass += 1) {
    const group = readBalanced(result, 0, "{", "}");
    if (!group || result.slice(group.end).trim().length > 0) break;
    result = result.slice(1, group.end - 1).trim();
  }

  return result;
};

const splitTopLevel = (value: string, separator: string): string[] => {
  const result: string[] = [];
  let start = 0;
  let braceDepth = 0;
  let bracketDepth = 0;
  let parenthesisDepth = 0;

  for (let cursor = 0; cursor < value.length; cursor += 1) {
    if (isEscapedAt(value, cursor)) continue;
    const character = value.charAt(cursor);
    if (character === "{") braceDepth += 1;
    if (character === "}" && braceDepth > 0) braceDepth -= 1;
    if (character === "[") bracketDepth += 1;
    if (character === "]" && bracketDepth > 0) bracketDepth -= 1;
    if (character === "(") parenthesisDepth += 1;
    if (character === ")" && parenthesisDepth > 0) parenthesisDepth -= 1;
    if (
      character === separator &&
      braceDepth === 0 &&
      bracketDepth === 0 &&
      parenthesisDepth === 0
    ) {
      result.push(value.slice(start, cursor));
      start = cursor + 1;
    }
  }

  result.push(value.slice(start));
  return result;
};

const findTopLevelEquals = (value: string): number => {
  let braceDepth = 0;
  let bracketDepth = 0;
  let parenthesisDepth = 0;

  for (let cursor = 0; cursor < value.length; cursor += 1) {
    if (isEscapedAt(value, cursor)) continue;
    const character = value.charAt(cursor);
    if (character === "{") braceDepth += 1;
    if (character === "}" && braceDepth > 0) braceDepth -= 1;
    if (character === "[") bracketDepth += 1;
    if (character === "]" && bracketDepth > 0) bracketDepth -= 1;
    if (character === "(") parenthesisDepth += 1;
    if (character === ")" && parenthesisDepth > 0) parenthesisDepth -= 1;
    if (
      character === "=" &&
      braceDepth === 0 &&
      bracketDepth === 0 &&
      parenthesisDepth === 0
    ) {
      return cursor;
    }
  }

  return -1;
};

const normalizeIdentifier = (value: string): string =>
  truncateCharacters(
    trimOuterBraces(stripComments(value))
      .replace(/\\([%&#_${}])/g, "$1")
      .replace(/\s+/g, " ")
      .trim(),
    MAX_IDENTIFIER_LENGTH,
  );

/** A deliberately small printable projection for a listing caption. */
const toPlainCaption = (value: string): string => {
  let text = trimOuterBraces(stripComments(value)).slice(0, MAX_OPTIONS_LENGTH);

  for (let pass = 0; pass < 6; pass += 1) {
    const previous = text;
    text = text
      .replace(/\\href\s*\{[^{}]*\}\s*\{([^{}]*)\}/g, "$1")
      .replace(TEXT_WRAPPERS, "$1");
    if (text === previous) break;
  }

  text = text
    .replace(/\\(?:label|ref|pageref|cite)\*?\s*\{[^{}]*\}/g, " ")
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

  return truncateCharacters(text, MAX_CAPTION_LENGTH);
};

const parseOptions = (rawOptions: string): ListingOptions => {
  const optionsWereTruncated = rawOptions.length > MAX_OPTIONS_LENGTH;
  const boundedOptions = stripComments(rawOptions.slice(0, MAX_OPTIONS_LENGTH));
  let language = "";
  let caption = "";
  let label = "";

  for (const part of splitTopLevel(boundedOptions, ",")) {
    const equals = findTopLevelEquals(part);
    if (equals < 0) continue;
    const key = part.slice(0, equals).trim().toLocaleLowerCase();
    const value = part.slice(equals + 1);
    if (key === "language") language = normalizeIdentifier(value);
    if (key === "caption") caption = toPlainCaption(value);
    if (key === "label") label = normalizeIdentifier(value);
  }

  return {
    language,
    caption,
    label,
    truncated: optionsWereTruncated,
  };
};

const findEnvironmentCommand = (
  source: string,
  pattern: RegExp,
  start = 0,
): RegExpExecArray | null => {
  pattern.lastIndex = start;
  let match = pattern.exec(source);
  while (match && isEscapedAt(source, match.index)) {
    match = pattern.exec(source);
  }
  return match;
};

const lineBound = (value: string): number => {
  if (value.length === 0) return 0;
  let lineCount = 1;

  for (let cursor = 0; cursor < value.length; cursor += 1) {
    const character = value.charAt(cursor);
    if (character !== "\n" && character !== "\r") continue;
    if (lineCount >= MAX_CODE_LINES) return cursor;
    lineCount += 1;
    if (character === "\r" && value.charAt(cursor + 1) === "\n") cursor += 1;
  }

  return value.length;
};

const boundCode = (value: string): { code: string; truncated: boolean } => {
  let end = Math.min(value.length, MAX_CODE_LENGTH, lineBound(value));
  const lastCodeUnit = value.charCodeAt(end - 1);
  const nextCodeUnit = value.charCodeAt(end);
  if (
    end > 0 &&
    end < value.length &&
    lastCodeUnit >= 0xd800 &&
    lastCodeUnit <= 0xdbff &&
    nextCodeUnit >= 0xdc00 &&
    nextCodeUnit <= 0xdfff
  ) {
    end -= 1;
  }
  return { code: value.slice(0, end), truncated: end < value.length };
};

/**
 * Parse the first uncommented `lstlisting` without interpreting its body.
 * All scans and returned strings are bounded for safe use in editor previews.
 */
export const parseListingPreview = (
  source: string | undefined,
): ListingPreview => {
  if (typeof source !== "string" || source.length === 0) return emptyPreview();

  try {
    const sourceWasTruncated = source.length > MAX_SOURCE_LENGTH;
    const scannedSource = source.slice(0, MAX_SOURCE_LENGTH);
    const structuralSource = maskComments(scannedSource);
    const begin = findEnvironmentCommand(
      structuralSource,
      /\\begin\s*\{\s*lstlisting\s*\}/g,
    );
    if (!begin) return emptyPreview(sourceWasTruncated);

    const beginEnd = begin.index + begin[0].length;
    const optionStart = skipWhitespace(structuralSource, beginEnd);
    let bodyStart = beginEnd;
    let optionsComplete = true;
    let options: ListingOptions = {
      language: "",
      caption: "",
      label: "",
      truncated: false,
    };

    if (structuralSource.charAt(optionStart) === "[") {
      const optionRange = readBalanced(structuralSource, optionStart, "[", "]");
      if (optionRange) {
        options = parseOptions(
          scannedSource.slice(optionStart + 1, optionRange.end - 1),
        );
        bodyStart = optionRange.end;
      } else {
        optionsComplete = false;
      }
    }

    const end = findEnvironmentCommand(
      scannedSource,
      /\\end\s*\{\s*lstlisting\s*\}/g,
      bodyStart,
    );
    const rawCode = scannedSource.slice(bodyStart, end?.index);
    const boundedCode = boundCode(rawCode);

    return {
      language: options.language,
      caption: options.caption,
      label: options.label,
      code: boundedCode.code,
      complete: optionsComplete && end !== null,
      truncated:
        options.truncated ||
        boundedCode.truncated ||
        (end === null && sourceWasTruncated),
    };
  } catch {
    return emptyPreview();
  }
};
