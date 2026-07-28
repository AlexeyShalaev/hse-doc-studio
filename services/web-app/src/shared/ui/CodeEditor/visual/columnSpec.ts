/**
 * Parse and edit a LaTeX table column specification — the `{|l|p{..}|X|}`
 * argument of `tabular`/`longtable`/… — so the visual editor can add, remove,
 * reorder and re-align columns without the user touching the raw spec.
 */

export type ColumnAlign = "left" | "center" | "right" | "other";

export type ParsedColumn = {
  /** Alignment token without borders, e.g. "l" or
   *  ">{\\raggedright\\arraybackslash}p{0.28\\textwidth}". */
  token: string;
  align: ColumnAlign;
  /** Verbatim border material (`|`, `@{..}`, spaces) to the column's left. */
  leftBorder: string;
};

export type ParsedColumnSpec = {
  columns: ParsedColumn[];
  /** Verbatim border material after the last column. */
  rightBorder: string;
};

type Group = { content: string; end: number };

const readGroup = (source: string, from: number): Group | undefined => {
  if (source.charAt(from) !== "{") return undefined;
  let depth = 1;
  for (let cursor = from + 1; cursor < source.length; cursor += 1) {
    const character = source.charAt(cursor);
    if (character === "\\") {
      cursor += 1;
      continue;
    }
    if (character === "{") depth += 1;
    else if (character === "}") {
      depth -= 1;
      if (depth === 0) {
        return { content: source.slice(from + 1, cursor), end: cursor + 1 };
      }
    }
  }
  return undefined;
};

const ALIGN_PREFIX: Record<Exclude<ColumnAlign, "other">, string> = {
  left: "\\raggedright",
  center: "\\centering",
  right: "\\raggedleft",
};

const alignFromToken = (prefix: string, typeChar: string): ColumnAlign => {
  if (/\\centering\b/.test(prefix)) return "center";
  if (/\\raggedleft\b/.test(prefix)) return "right";
  if (/\\raggedright\b/.test(prefix)) return "left";
  if (typeChar === "c") return "center";
  if (typeChar === "r") return "right";
  if (typeChar === "l") return "left";
  return "left"; // p/m/b/X/w default to (justified) left
};

/** Read one column starting at `cursor` (after borders). Returns null if none. */
const readColumn = (
  source: string,
  start: number,
): { token: string; typeChar: string; prefix: string; end: number } | null => {
  let cursor = start;
  let prefix = "";
  while (source.charAt(cursor) === ">") {
    const group = readGroup(source, cursor + 1);
    if (!group) break;
    prefix += source.slice(cursor, group.end);
    cursor = group.end;
  }
  const typeChar = source.charAt(cursor);
  if (typeChar === "") return null;
  let token = prefix + typeChar;
  cursor += 1;
  // w/W take an alignment group then a width group; p/m/b take a width group.
  if (typeChar === "w" || typeChar === "W") {
    const alignGroup = readGroup(source, cursor);
    if (alignGroup) {
      token += source.slice(cursor, alignGroup.end);
      cursor = alignGroup.end;
    }
  }
  if ("pmbwW".includes(typeChar)) {
    const width = readGroup(source, cursor);
    if (width) {
      token += source.slice(cursor, width.end);
      cursor = width.end;
    }
  }
  while (source.charAt(cursor) === "<") {
    const group = readGroup(source, cursor + 1);
    if (!group) break;
    token += source.slice(cursor, group.end);
    cursor = group.end;
  }
  return { token, typeChar, prefix, end: cursor };
};

/** Parse a column-spec string (the content between the `{ }`). */
export const parseColumnSpec = (spec: string): ParsedColumnSpec => {
  const columns: ParsedColumn[] = [];
  let border = "";
  let cursor = 0;

  while (cursor < spec.length) {
    const character = spec.charAt(cursor);
    if (/\s/.test(character) || character === "|") {
      border += character;
      cursor += 1;
      continue;
    }
    if (character === "@" || character === "!") {
      const group = readGroup(spec, cursor + 1);
      const end = group ? group.end : cursor + 1;
      border += spec.slice(cursor, end);
      cursor = end;
      continue;
    }
    if (character === "*") {
      // *{n}{cols} → expand n copies of the sub-spec.
      const count = readGroup(spec, cursor + 1);
      const sub = count ? readGroup(spec, count.end) : undefined;
      if (count && sub) {
        const repeats = Math.max(
          0,
          Number.parseInt(count.content.trim(), 10) || 0,
        );
        const inner = parseColumnSpec(sub.content).columns;
        for (let copy = 0; copy < repeats; copy += 1) {
          inner.forEach((column, index) => {
            columns.push({
              ...column,
              leftBorder:
                copy === 0 && index === 0
                  ? border + column.leftBorder
                  : column.leftBorder,
            });
          });
          if (copy === 0) border = "";
        }
        border = "";
        cursor = sub.end;
        continue;
      }
      // Malformed — treat the star as inert border material.
      border += character;
      cursor += 1;
      continue;
    }
    const column = readColumn(spec, cursor);
    if (!column) {
      border += character;
      cursor += 1;
      continue;
    }
    columns.push({
      token: column.token,
      align: alignFromToken(column.prefix, column.typeChar),
      leftBorder: border,
    });
    border = "";
    cursor = column.end;
  }

  return { columns, rightBorder: border };
};

/** Serialize a parsed spec back to the `{ }` content. */
export const serializeColumnSpec = (spec: ParsedColumnSpec): string =>
  spec.columns.map((column) => column.leftBorder + column.token).join("") +
  spec.rightBorder;

/** Strip a leading `>{…}` alignment prefix, returning the rest of the token. */
const stripAlignPrefix = (token: string): string => {
  let rest = token;
  while (rest.startsWith(">")) {
    const group = readGroup(rest, 1);
    if (!group) break;
    if (/\\(?:raggedright|centering|raggedleft)\b/.test(group.content)) {
      rest = rest.slice(group.end);
      continue;
    }
    break;
  }
  return rest;
};

/**
 * Retarget a column token to a new alignment, preserving the column type and
 * any `p{width}`. Simple `l`/`c`/`r` swap the letter; paragraph columns swap a
 * `>{\\raggedX\\arraybackslash}` prefix.
 */
export const retargetAlign = (token: string, align: ColumnAlign): string => {
  if (align === "other") return token;
  const base = stripAlignPrefix(token);
  const typeChar = base.charAt(0);
  if ("lcr".includes(typeChar) && base.length === 1) {
    return align === "center" ? "c" : align === "right" ? "r" : "l";
  }
  return `>{${ALIGN_PREFIX[align]}\\arraybackslash}${base}`;
};

/** A sensible token for a new column: mirror a sibling, else plain `l`. */
export const defaultColumnToken = (sibling: string | null): string =>
  sibling && sibling.trim() !== "" ? sibling : "l";
