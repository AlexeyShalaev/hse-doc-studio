const MAX_SOURCE_LENGTH = 256_000;
const MAX_BIBITEM_CANDIDATES = 400;
const MAX_ENTRIES = 100;
const MAX_ENTRY_SOURCE_LENGTH = 16_000;
const MAX_ENTRY_TEXT_LENGTH = 1_000;
const MAX_KEY_LENGTH = 160;

const TEXT_WRAPPERS =
  /\\(?:textbf|textit|emph|underline|textrm|textsf|texttt|textsc|textsuperscript|textsubscript|mbox|makecell|MakeUppercase|MakeLowercase)\*?\s*\{([^{}]*)\}/g;

export type BibliographyPreviewEntry = {
  key: string;
  text: string;
};

export type BibliographyPreview = {
  entries: BibliographyPreviewEntry[];
  complete: boolean;
  truncated: boolean;
};

type BalancedRange = {
  end: number;
};

type ParsedBibitem = {
  key: string;
  bodyStart: number;
  truncated: boolean;
};

const emptyPreview = (truncated = false): BibliographyPreview => ({
  entries: [],
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

/** Replace comments with spaces so matches retain offsets into the source. */
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

const truncateCharacters = (
  value: string,
  limit: number,
): { value: string; truncated: boolean } => {
  const characters = Array.from(value);
  if (characters.length <= limit) return { value, truncated: false };
  return {
    value: `${characters.slice(0, Math.max(0, limit - 1)).join("")}…`,
    truncated: true,
  };
};

/** A small printable projection; it never expands or evaluates TeX commands. */
const toPlainText = (
  rawValue: string,
): { text: string; truncated: boolean } => {
  const sourceWasTruncated = rawValue.length > MAX_ENTRY_SOURCE_LENGTH;
  let text = stripComments(rawValue.slice(0, MAX_ENTRY_SOURCE_LENGTH));

  for (let pass = 0; pass < 8; pass += 1) {
    const previous = text;
    text = text
      .replace(/\\url\s*\{([^{}]*)\}/g, "$1")
      .replace(/\\href\s*\{[^{}]*\}\s*\{([^{}]*)\}/g, "$1")
      .replace(
        /\\(?:textcolor|colorbox|foreignlanguage)\s*\{[^{}]*\}\s*\{([^{}]*)\}/g,
        "$1",
      )
      .replace(TEXT_WRAPPERS, "$1");
    if (text === previous) break;
  }

  text = text
    .replace(/\\(?:label|cite|citep|citet|ref|pageref)\*?\s*\{[^{}]*\}/g, " ")
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

  const boundedText = truncateCharacters(text, MAX_ENTRY_TEXT_LENGTH);
  return {
    text: boundedText.value,
    truncated: sourceWasTruncated || boundedText.truncated,
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

const parseBibitem = (
  source: string,
  structuralSource: string,
  commandEnd: number,
): ParsedBibitem | null => {
  let cursor = skipWhitespace(structuralSource, commandEnd);
  if (structuralSource.charAt(cursor) === "[") {
    const optionalLabel = readBalanced(structuralSource, cursor, "[", "]");
    if (!optionalLabel) return null;
    cursor = skipWhitespace(structuralSource, optionalLabel.end);
  }

  const keyRange = readBalanced(structuralSource, cursor, "{", "}");
  if (!keyRange) return null;
  const rawKey = stripComments(source.slice(cursor + 1, keyRange.end - 1))
    .replace(/\\([%&#_${}])/g, "$1")
    .replace(/\s+/g, " ")
    .trim();
  const boundedKey = truncateCharacters(rawKey, MAX_KEY_LENGTH);
  if (boundedKey.value.length === 0) return null;

  return {
    key: boundedKey.value,
    bodyStart: keyRange.end,
    truncated: boundedKey.truncated,
  };
};

/**
 * Parse the first uncommented `thebibliography` into inert printable strings.
 * Malformed items are skipped, while all scans and outputs remain bounded.
 */
export const parseBibliographyPreview = (
  source: string | undefined,
): BibliographyPreview => {
  if (typeof source !== "string" || source.length === 0) return emptyPreview();

  try {
    const sourceWasTruncated = source.length > MAX_SOURCE_LENGTH;
    const scannedSource = source.slice(0, MAX_SOURCE_LENGTH);
    const structuralSource = maskComments(scannedSource);
    const begin = findEnvironmentCommand(
      structuralSource,
      /\\begin\s*\{\s*thebibliography\s*\}/g,
    );
    if (!begin) return emptyPreview(sourceWasTruncated);

    const beginEnd = begin.index + begin[0].length;
    const widestLabelStart = skipWhitespace(structuralSource, beginEnd);
    const widestLabel = readBalanced(
      structuralSource,
      widestLabelStart,
      "{",
      "}",
    );
    const bodyStart = widestLabel?.end ?? beginEnd;
    const end = findEnvironmentCommand(
      structuralSource,
      /\\end\s*\{\s*thebibliography\s*\}/g,
      bodyStart,
    );
    const bodyEnd = end?.index ?? scannedSource.length;
    const entries: BibliographyPreviewEntry[] = [];
    let current: ParsedBibitem | null = null;
    let truncated = false;
    let candidateCount = 0;
    const itemPattern = /\\bibitem\b/g;
    itemPattern.lastIndex = bodyStart;

    const appendCurrent = (entryEnd: number): void => {
      if (!current) return;
      if (entries.length >= MAX_ENTRIES) {
        truncated = true;
        current = null;
        return;
      }
      const printable = toPlainText(
        scannedSource.slice(current.bodyStart, entryEnd),
      );
      entries.push({ key: current.key, text: printable.text });
      truncated ||= current.truncated || printable.truncated;
      current = null;
    };

    let match = itemPattern.exec(structuralSource);
    while (match && match.index < bodyEnd) {
      if (isEscapedAt(structuralSource, match.index)) {
        match = itemPattern.exec(structuralSource);
        continue;
      }
      appendCurrent(match.index);
      if (candidateCount >= MAX_BIBITEM_CANDIDATES) {
        truncated = true;
        break;
      }
      candidateCount += 1;
      current = parseBibitem(
        scannedSource,
        structuralSource,
        match.index + match[0].length,
      );
      match = itemPattern.exec(structuralSource);
    }
    appendCurrent(bodyEnd);

    return {
      entries,
      complete: widestLabel !== null && end !== null,
      truncated: truncated || (end === null && sourceWasTruncated),
    };
  } catch {
    return emptyPreview();
  }
};
