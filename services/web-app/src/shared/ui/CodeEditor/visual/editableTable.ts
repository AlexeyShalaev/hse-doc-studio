import { escapeLatex } from "./cellRichText";
import {
  defaultColumnToken,
  parseColumnSpec,
  retargetAlign,
  serializeColumnSpec,
  type ColumnAlign,
} from "./columnSpec";

/**
 * A structured, editable view of a LaTeX table for the visual table editor.
 * Parsing splits the table into an immutable {@link TableScaffold} (the
 * `\begin{…}` wrapper, regenerable column spec and head/foot structure) and an
 * editable {@link DraftTable} (columns with alignment/label/wrapper templates
 * and inline-LaTeX cell values). The draft is what the modal edits and undoes;
 * {@link serializeEditableTable} regenerates valid LaTeX from scaffold + draft.
 */

export type { ColumnAlign } from "./columnSpec";

const TABLE_ENVIRONMENTS = [
  "longtable",
  "xltabular",
  "tabularx",
  "tabulary",
  "tabular*",
  "tabular",
] as const;

const HEAD_MARKERS = ["endfirsthead", "endhead", "endfoot", "endlastfoot"];

/** How a column's data cells are wrapped, so edits/new rows keep the wrapper. */
export type ColumnTemplate =
  | { kind: "plain" }
  | { kind: "wrap"; prefix: string; suffix: string }
  | { kind: "req" };

export type DraftColumn = {
  /** Header label as plain text; wrapped by the head template on serialize. */
  label: string;
  align: ColumnAlign;
  /** Column-spec token (align/width/prefix), without borders. */
  token: string;
  /** Verbatim border material to the column's left (`|`, `@{…}`…). */
  leftBorder: string;
  template: ColumnTemplate;
  /** This column supplies the id for `\req{id}{…}` cells (tracked by identity
   *  so it survives reordering). */
  isIdColumn: boolean;
  /** Original header cell source; emitted verbatim while the label is unchanged
   *  so nested markup/math in a header survives round-trip. Null = new column. */
  headerRaw: string | null;
};

export type DraftCell = {
  /** Inline LaTeX shown (rendered) in the rich cell editor. */
  value: string;
  /** Original full cell source (null for new cells) — kept for exact round-trip. */
  raw: string | null;
  /** The value at parse time; `value === pristine` ⇒ emit `raw` verbatim. */
  pristine: string;
  /** For a `\req{id}{…}` cell, the id parsed from the source — the fallback id
   *  when the id column is deleted. */
  reqId: string;
};

export type DraftTable = {
  columns: DraftColumn[];
  rows: DraftCell[][];
  /** The `\\` terminator suffix of each data row (`[6pt]`, `*`, …), by index. */
  rowBreaks: string[];
  /** Rule material (`\hline`/`\cline{…}`) that precedes each data row, by index
   *  — captured verbatim so borderless/partial rules round-trip exactly. */
  rowRules: string[];
  /** Rule material after the last data row (e.g. a closing `\hline`). Lives on
   *  the draft (not the scaffold) so column ops degrade its `\cline`s too. */
  finalRule: string;
};

type HeadNode =
  | { kind: "verbatim"; lead: string; content: string }
  | { kind: "header"; lead: string }
  | {
      kind: "multicolumn";
      lead: string;
      rest: string;
      /** The original span count. Only rewritten when it spanned all columns. */
      span: number;
      fullSpan: boolean;
    };

export type TableScaffold = {
  /** `\begin{env}[pos]{width}{` through the column spec's opening brace. */
  openBefore: string;
  /** The column spec's closing brace and anything after it in the open token. */
  openAfter: string;
  rightBorder: string;
  headNodes: HeadNode[];
  /** Trailing head scaffolding after the last `\\` (e.g. `\hline …\endlastfoot`). */
  headTrailing: string;
  headerWrap: "textbf" | "none";
  close: string;
  /** All cells round-trip safely (no multicolumn/multirow/nested envs). */
  editable: boolean;
  /** The head can be regenerated, so columns may be added/removed. */
  canEditColumns: boolean;
};

export type ParsedEditableTable = {
  scaffold: TableScaffold;
  draft: DraftTable;
};

// ---------------------------------------------------------------------------
// Low-level LaTeX scanning helpers.
// ---------------------------------------------------------------------------

const isControlWordCharacter = (character: string): boolean =>
  /[A-Za-z@]/.test(character);

const stripComments = (source: string): string => {
  let output = "";
  for (let cursor = 0; cursor < source.length; cursor += 1) {
    const character = source.charAt(cursor);
    if (character === "\\") {
      output += character + (source.charAt(cursor + 1) || "");
      cursor += 1;
      continue;
    }
    if (character !== "%") {
      output += character;
      continue;
    }
    while (cursor < source.length && source.charAt(cursor) !== "\n")
      cursor += 1;
    if (cursor < source.length) output += "\n";
  }
  return output;
};

const skipWhitespace = (source: string, from: number): number => {
  let cursor = from;
  while (cursor < source.length && /\s/.test(source.charAt(cursor)))
    cursor += 1;
  return cursor;
};

type Group = { content: string; end: number };

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
    if (character === opening) depth += 1;
    else if (character === closing) {
      depth -= 1;
      if (depth === 0) {
        return { content: source.slice(from + 1, cursor), end: cursor + 1 };
      }
    }
  }
  return undefined;
};

type RowSplit = { segments: string[]; breaks: string[] };

/**
 * Split a table body into physical rows by top-level `\\`, capturing each
 * break's optional `*` / `[dim]` suffix so it round-trips. `breaks[i]` is the
 * suffix after `segments[i]`'s `\\` (last segment has no trailing `\\`).
 */
const splitRowBreaks = (body: string): RowSplit => {
  const segments: string[] = [];
  const breaks: string[] = [];
  let current = "";
  let depth = 0;
  for (let cursor = 0; cursor < body.length; cursor += 1) {
    const character = body.charAt(cursor);
    if (character === "\\") {
      const next = body.charAt(cursor + 1);
      if (next === "\\" && depth === 0) {
        segments.push(current);
        current = "";
        cursor += 1; // now at the second backslash
        let suffix = "";
        if (body.charAt(cursor + 1) === "*") {
          suffix += "*";
          cursor += 1;
        }
        const after = skipWhitespace(body, cursor + 1);
        if (body.charAt(after) === "[") {
          const spacing = readGroup(body, after, "[", "]");
          if (spacing) {
            suffix += body.slice(after, spacing.end);
            cursor = spacing.end - 1;
          } else {
            cursor = after - 1;
          }
        } else {
          cursor = after - 1;
        }
        breaks.push(suffix);
        continue;
      }
      current += character + (next || "");
      cursor += 1;
      continue;
    }
    current += character;
    if (character === "{") depth += 1;
    if (character === "}" && depth > 0) depth -= 1;
  }
  segments.push(current);
  return { segments, breaks };
};

/** Split a physical row into raw cells by top-level `&`. */
const splitCells = (row: string): string[] => {
  const cells: string[] = [];
  let current = "";
  let depth = 0;
  for (let cursor = 0; cursor < row.length; cursor += 1) {
    const character = row.charAt(cursor);
    if (character === "\\") {
      current += character + (row.charAt(cursor + 1) || "");
      cursor += 1;
      continue;
    }
    if (character === "{") depth += 1;
    if (character === "}" && depth > 0) depth -= 1;
    if (character === "&" && depth === 0) {
      cells.push(current);
      current = "";
      continue;
    }
    current += character;
  }
  cells.push(current);
  return cells;
};

const HEAD_LEAD_RE = new RegExp(
  `^((?:\\s*(?:\\\\hline|\\\\cline\\s*\\{[^}]*\\}|${HEAD_MARKERS.map(
    (marker) => `\\\\${marker}`,
  ).join("|")}))*\\s*)`,
);

const RULE_TOKEN_RE = /\\hline|\\cline\s*\{[^}]*\}/g;
const LEADING_RULE_RE = /^(?:\s*(?:\\hline|\\cline\s*\{[^}]*\}))*\s*/;

/** Split a data-row segment into its leading rule material and cell content. */
const splitLeadingRule = (
  segment: string,
): { rule: string; content: string } => {
  const match = LEADING_RULE_RE.exec(segment);
  const lead = match ? match[0] : "";
  const rule = (lead.match(RULE_TOKEN_RE) ?? []).join("\n");
  const content = segment
    .slice(lead.length)
    .replace(/(?:\s*(?:\\hline|\\cline\s*\{[^}]*\}))*\s*$/, "")
    .trim();
  return { rule, content };
};

const WRAP_COMMANDS = new Set([
  "textbf",
  "textit",
  "emph",
  "underline",
  "textrm",
  "textsf",
  "texttt",
  "textnormal",
  "mbox",
  "makecell",
]);

const SYMBOL: Record<string, string> = {
  ldots: "…",
  dots: "…",
  textellipsis: "…",
  textendash: "–",
  textemdash: "—",
};

/** Render a header cell's LaTeX down to plain label text. */
const renderLabel = (raw: string): string => {
  const source = raw.trim();
  let output = "";
  for (let cursor = 0; cursor < source.length; cursor += 1) {
    const character = source.charAt(cursor);
    if (character === "~") {
      output += " ";
      continue;
    }
    if (character === "{" || character === "}") continue;
    if (character !== "\\") {
      output += character;
      continue;
    }
    const escaped = source.charAt(cursor + 1);
    if ("&%$#_{}".includes(escaped)) {
      output += escaped;
      cursor += 1;
      continue;
    }
    if (escaped === "\\") {
      output += " ";
      cursor += 1;
      continue;
    }
    let end = cursor + 1;
    while (end < source.length && isControlWordCharacter(source.charAt(end)))
      end += 1;
    const name = source.slice(cursor + 1, end);
    cursor = end - 1;
    if (WRAP_COMMANDS.has(name)) {
      const argument = readGroup(source, skipWhitespace(source, cursor + 1));
      if (argument) {
        output += renderLabel(argument.content);
        cursor = argument.end - 1;
      }
      continue;
    }
    const glyph = SYMBOL[name];
    if (glyph !== undefined) output += glyph;
  }
  return output.replace(/\s+/g, " ").trim();
};

const REQ_RE = /^\\req\s*\{[^{}]*\}\s*\{[\s\S]*\}$/;
const WRAP_RE =
  /^\\(textbf|textit|emph|underline|textrm|textsf|texttt)\s*\{([\s\S]*)\}$/;
const COMPLEX_RE = /\\(multicolumn|multirow)\b|\\begin\s*\{/;

/** The inner content of a cell, given its column template. */
const extractInner = (raw: string, template: ColumnTemplate): string => {
  const trimmed = raw.trim();
  if (template.kind === "req") {
    const id = readGroup(trimmed, skipWhitespace(trimmed, "\\req".length));
    const body = id
      ? readGroup(trimmed, skipWhitespace(trimmed, id.end))
      : null;
    return body ? body.content.trim() : trimmed;
  }
  if (template.kind === "wrap") {
    const match = WRAP_RE.exec(trimmed);
    return match ? (match[2] ?? "").trim() : trimmed;
  }
  return trimmed;
};

/** The id argument of a `\req{id}{…}` cell (plain), or "". */
const extractReqId = (raw: string): string => {
  const trimmed = raw.trim();
  const id = readGroup(trimmed, skipWhitespace(trimmed, "\\req".length));
  return id ? id.content.trim() : "";
};

const ID_WRAP_RE =
  /^\\(?:textbf|textit|emph|underline|textrm|textsf|texttt|textnormal|mbox)\s*\{([\s\S]*)\}$/;

/**
 * A `\req` id reduced to a plain identifier: strip only outer formatting
 * wrappers (so a bolded id cell doesn't leak `\textbf` into the key), but keep
 * everything else (`~`, `\ldots`, …) verbatim so ids with those still match.
 */
const plainId = (value: string): string => {
  let result = value.trim();
  for (let guard = 0; guard < 8; guard += 1) {
    const match = ID_WRAP_RE.exec(result);
    if (!match) break;
    result = (match[1] ?? "").trim();
  }
  return result;
};

const isBoldHeaderRow = (cells: readonly string[]): boolean =>
  cells.length >= 2 &&
  cells.every((cell) => /\\(?:textbf|bfseries)\b/.test(cell));

const detectTemplates = (
  rawRows: string[][],
  columns: number,
): ColumnTemplate[] => {
  const templates: ColumnTemplate[] = [];
  for (let column = 0; column < columns; column += 1) {
    const cells = rawRows
      .map((row) => (row[column] ?? "").trim())
      .filter((cell) => cell !== "");
    if (cells.length === 0) {
      templates.push({ kind: "plain" });
      continue;
    }
    if (cells.every((cell) => REQ_RE.test(cell))) {
      templates.push({ kind: "req" });
      continue;
    }
    const commands = cells.map((cell) => WRAP_RE.exec(cell)?.[1]);
    const first = commands[0];
    if (first && commands.every((command) => command === first)) {
      templates.push({ kind: "wrap", prefix: `\\${first}{`, suffix: "}" });
      continue;
    }
    templates.push({ kind: "plain" });
  }
  return templates;
};

// ---------------------------------------------------------------------------
// Head (longtable head/foot) structuring.
// ---------------------------------------------------------------------------

type ParsedHead = {
  nodes: HeadNode[];
  trailing: string;
  headerWrap: "textbf" | "none";
  labels: string[];
  /** Raw header cells of the first header row (for verbatim round-trip). */
  headerCells: string[];
  /** A verbatim head row carried multiple cells → column edits are unsafe. */
  ambiguous: boolean;
};

const splitLead = (piece: string): { lead: string; content: string } => {
  const match = HEAD_LEAD_RE.exec(piece);
  const lead = match ? match[0] : "";
  return { lead, content: piece.slice(lead.length).trim() };
};

const parseHead = (head: string, columnCount: number): ParsedHead => {
  const pieces = splitRowBreaks(head).segments;
  const trailing = pieces.length > 0 ? (pieces[pieces.length - 1] ?? "") : "";
  const bodyPieces = pieces.slice(0, -1);
  const nodes: HeadNode[] = [];
  let headerWrap: "textbf" | "none" = "none";
  let labels: string[] = [];
  let headerCells: string[] = [];
  let ambiguous = false;

  for (const piece of bodyPieces) {
    const { lead, content } = splitLead(piece);
    if (
      content.startsWith("\\multicolumn") &&
      splitCells(content).length === 1
    ) {
      const count = readGroup(
        content,
        skipWhitespace(content, "\\multicolumn".length),
      );
      const rest = count ? content.slice(count.end) : content;
      const span = count
        ? Number.parseInt(count.content.trim(), 10) || columnCount
        : columnCount;
      nodes.push({
        kind: "multicolumn",
        lead,
        rest,
        span,
        fullSpan: span === columnCount,
      });
      continue;
    }
    const cells = splitCells(content);
    if (cells.length >= 2 && isBoldHeaderRow(cells)) {
      if (labels.length === 0) {
        headerWrap = "textbf";
        headerCells = cells.map((cell) => cell.trim());
        labels = headerCells.map((cell) => renderLabel(cell));
      }
      nodes.push({ kind: "header", lead });
      continue;
    }
    if (cells.length >= 2) ambiguous = true; // an unrecognized multi-cell row
    nodes.push({ kind: "verbatim", lead, content });
  }

  return { nodes, trailing, headerWrap, labels, headerCells, ambiguous };
};

// ---------------------------------------------------------------------------
// Parsing.
// ---------------------------------------------------------------------------

const environmentRegExp = (name: string, command: "begin" | "end"): RegExp =>
  new RegExp(`\\\\${command}\\s*\\{\\s*${name.replace("*", "\\*")}\\s*\\}`);

/** Parse the first supported table environment, or null when there is none. */
export const parseEditableTable = (
  source: string | undefined,
): ParsedEditableTable | null => {
  if (!source) return null;
  const text = stripComments(source);

  let environment: string | undefined;
  let beginStart = -1;
  for (const name of TABLE_ENVIRONMENTS) {
    const match = environmentRegExp(name, "begin").exec(text);
    if (match && (beginStart === -1 || match.index < beginStart)) {
      environment = name;
      beginStart = match.index;
    }
  }
  if (!environment || beginStart === -1) return null;

  const beginToken = environmentRegExp(environment, "begin").exec(
    text.slice(beginStart),
  );
  if (!beginToken) return null;
  let cursor = beginStart + beginToken[0].length;

  cursor = skipWhitespace(text, cursor);
  if (text.charAt(cursor) === "[") {
    const position = readGroup(text, cursor, "[", "]");
    if (position) cursor = position.end;
  }
  // tabularx/xltabular/tabular*/tabulary take a mandatory width group BEFORE
  // the column spec; the others take only the column spec.
  const argumentCount =
    environment === "tabularx" ||
    environment === "xltabular" ||
    environment === "tabular*" ||
    environment === "tabulary"
      ? 2
      : 1;
  let specOpen = -1;
  let specGroup: Group | undefined;
  for (let index = 0; index < argumentCount; index += 1) {
    cursor = skipWhitespace(text, cursor);
    specOpen = cursor;
    const argument = readGroup(text, cursor);
    if (!argument) return null;
    specGroup = argument;
    cursor = argument.end;
  }
  if (specOpen < 0 || !specGroup) return null;
  const openBefore = text.slice(beginStart, specOpen + 1);
  const openAfter = text.slice(specGroup.end - 1, cursor);
  const parsedSpec = parseColumnSpec(specGroup.content);

  const endToken = environmentRegExp(environment, "end").exec(
    text.slice(cursor),
  );
  if (!endToken) return null;
  const body = text.slice(cursor, cursor + endToken.index);
  const close = endToken[0];

  let headEnd = 0;
  for (const marker of HEAD_MARKERS) {
    const match = new RegExp(`\\\\${marker}\\b`).exec(body);
    if (match) headEnd = Math.max(headEnd, match.index + match[0].length);
  }
  const headText = headEnd > 0 ? body.slice(0, headEnd) : "";
  const dataRegion = body.slice(headEnd);

  const mergeRule = (before: string, after: string): string =>
    before === "" ? after : after === "" ? before : `${before}\n${after}`;
  const dataSplit = splitRowBreaks(dataRegion);
  const dataEntries: { content: string; brk: string; rule: string }[] = [];
  // A content-less segment carries only rule material; fold its rule into the
  // next data row (or into finalRule when it is trailing) so it isn't lost.
  let pendingRule = "";
  dataSplit.segments.forEach((segment, index) => {
    const { rule, content } = splitLeadingRule(segment);
    if (content === "") {
      pendingRule = mergeRule(pendingRule, rule);
      return;
    }
    dataEntries.push({
      content,
      brk: dataSplit.breaks[index] ?? "",
      rule: mergeRule(pendingRule, rule),
    });
    pendingRule = "";
  });
  const finalRule = pendingRule;
  let rawRows = dataEntries.map((entry) =>
    splitCells(entry.content).map((cell) => cell.trim()),
  );
  let rowBreaks = dataEntries.map((entry) => entry.brk);
  let rowRules = dataEntries.map((entry) => entry.rule);

  const head = parseHead(headText, parsedSpec.columns.length);
  let headNodes = head.nodes;
  const headTrailing = head.trailing;
  let headerWrap = head.headerWrap;
  let labels = head.labels;
  let headerCells = head.headerCells;
  const ambiguous = head.ambiguous;

  // A plain tabular keeps its header as the first data row; lift an all-bold
  // header into the scaffolding so it shows as column labels, not a data row.
  // Its leading rule (if any) becomes the header node's lead — a borderless
  // table stays borderless, a ruled one keeps its rule.
  const firstRow = rawRows[0];
  if (
    headEnd === 0 &&
    rawRows.length > 1 &&
    firstRow &&
    isBoldHeaderRow(firstRow)
  ) {
    headerCells = firstRow;
    labels = firstRow.map((cell) => renderLabel(cell));
    headerWrap = "textbf";
    const headerRule = rowRules[0] ?? "";
    headNodes = [{ kind: "header", lead: headerRule ? `${headerRule}\n` : "" }];
    rawRows = rawRows.slice(1);
    rowBreaks = rowBreaks.slice(1);
    rowRules = rowRules.slice(1);
  }

  const columns = Math.max(
    parsedSpec.columns.length,
    labels.length,
    ...rawRows.map((row) => row.length),
    1,
  );
  const padded = rawRows.map((row) => {
    const next = row.slice(0, columns);
    while (next.length < columns) next.push("");
    return next;
  });
  const templates = detectTemplates(padded, columns);

  const hasReq = templates.some((template) => template.kind === "req");
  const draftColumns: DraftColumn[] = [];
  for (let index = 0; index < columns; index += 1) {
    const spec = parsedSpec.columns[index];
    const token = spec ? spec.token : defaultColumnToken(null);
    draftColumns.push({
      label: labels[index] ?? "",
      align: spec ? spec.align : "left",
      token,
      leftBorder: spec
        ? spec.leftBorder
        : index === 0
          ? (parsedSpec.columns[0]?.leftBorder ?? "")
          : "",
      template: templates[index] ?? { kind: "plain" },
      // The first column supplies `\req` ids by convention.
      isIdColumn: hasReq && index === 0,
      headerRaw: headerCells[index] ?? null,
    });
  }

  const rows: DraftCell[][] = padded.map((row) =>
    row.map((raw, columnIndex) => {
      const template = templates[columnIndex] ?? { kind: "plain" };
      const value = extractInner(raw, template);
      const reqId = template.kind === "req" ? extractReqId(raw) : "";
      return { value, raw, pristine: value, reqId };
    }),
  );

  const editable = padded.every((row) =>
    row.every((cell) => !COMPLEX_RE.test(cell)),
  );

  return {
    scaffold: {
      openBefore,
      openAfter,
      rightBorder: parsedSpec.rightBorder,
      headNodes,
      headTrailing,
      headerWrap,
      close,
      editable,
      canEditColumns: editable && !ambiguous,
    },
    draft: { columns: draftColumns, rows, rowBreaks, rowRules, finalRule },
  };
};

// ---------------------------------------------------------------------------
// Serialization.
// ---------------------------------------------------------------------------

const headerCell = (label: string, wrap: "textbf" | "none"): string =>
  wrap === "textbf" ? `\\textbf{${escapeLatex(label)}}` : escapeLatex(label);

const DEFAULT_COLUMN: DraftColumn = {
  label: "",
  align: "left",
  token: "l",
  leftBorder: "",
  template: { kind: "plain" },
  isIdColumn: false,
  headerRaw: null,
};

const cellSource = (
  column: DraftColumn,
  cell: DraftCell,
  id: string,
): string => {
  if (column.template.kind === "req") {
    return `\\req{${id}}{${cell.value}}`;
  }
  if (cell.raw !== null && cell.value === cell.pristine) return cell.raw;
  if (column.template.kind === "wrap") {
    return `${column.template.prefix}${cell.value}${column.template.suffix}`;
  }
  return cell.value;
};

const renderHeadNode = (
  node: HeadNode,
  draft: DraftTable,
  headerWrap: "textbf" | "none",
): string => {
  if (node.kind === "verbatim") {
    return `${node.lead}${node.content} \\\\`;
  }
  if (node.kind === "multicolumn") {
    // Only a full-width spanner (\multicolumn{N} with N == column count) tracks
    // the column count; a deliberate partial span keeps its original count.
    const count = node.fullSpan ? draft.columns.length : node.span;
    return `${node.lead}\\multicolumn{${String(count)}}${node.rest} \\\\`;
  }
  const cells = draft.columns
    .map((column) =>
      // Emit the original header cell verbatim while its label is unchanged, so
      // nested markup/math in a header survives round-trip.
      column.headerRaw !== null &&
      renderLabel(column.headerRaw) === column.label
        ? column.headerRaw
        : headerCell(column.label, headerWrap),
    )
    .join(" & ");
  return `${node.lead}${cells} \\\\`;
};

export const serializeEditableTable = (
  scaffold: TableScaffold,
  draft: DraftTable,
): string => {
  const spec = serializeColumnSpec({
    columns: draft.columns.map((column) => ({
      token: column.token,
      align: column.align,
      leftBorder: column.leftBorder,
    })),
    rightBorder: scaffold.rightBorder,
  });
  const open = `${scaffold.openBefore}${spec}${scaffold.openAfter}`;

  const headParts = scaffold.headNodes.map((node) =>
    renderHeadNode(node, draft, scaffold.headerWrap),
  );
  const trailing = scaffold.headTrailing.trim();
  if (trailing !== "") headParts.push(trailing);
  const head = headParts.length > 0 ? `${headParts.join("\n")}\n` : "";

  const idColumn = draft.columns.findIndex((column) => column.isIdColumn);
  const dataRows = draft.rows.map((row, rowIndex) => {
    // The id is a plain identifier (outer formatting stripped, ~/\ldots kept).
    // `idNow` is the id column's current value; `idWas` its parse-time value.
    const idNow = idColumn >= 0 ? plainId(row[idColumn]?.value ?? "") : "";
    const idWas = idColumn >= 0 ? plainId(row[idColumn]?.pristine ?? "") : "";
    const cells = row
      .map((cell, columnIndex) => {
        // A \req cell adopts the id column's value only when it is the LINKED
        // req cell (a different column whose own parsed id matched the id
        // column); otherwise it keeps its own id. This avoids overwriting a
        // second \req column's distinct id, or an id column that is itself \req.
        // Both sides are plainId-normalized so ids with ~/\_/braces still link.
        const linked =
          idColumn >= 0 &&
          idColumn !== columnIndex &&
          plainId(cell.reqId) === idWas;
        const id = linked ? idNow : plainId(cell.reqId);
        return cellSource(
          draft.columns[columnIndex] ?? DEFAULT_COLUMN,
          cell,
          id,
        );
      })
      .join(" & ");
    const rule = draft.rowRules[rowIndex] ?? "";
    const lead = rule === "" ? "" : `${rule}\n`;
    return `${lead}${cells} \\\\${draft.rowBreaks[rowIndex] ?? ""}`;
  });
  const trailer = draft.finalRule === "" ? "" : `${draft.finalRule}\n`;
  const body =
    dataRows.length === 0 ? "" : `${dataRows.join("\n")}\n${trailer}`;

  return `${open}\n${head}${body}${scaffold.close}`;
};

// ---------------------------------------------------------------------------
// Pure editing operations on the draft.
// ---------------------------------------------------------------------------

const emptyCell = (): DraftCell => ({
  value: "",
  raw: null,
  pristine: "",
  reqId: "",
});

export const setCellValue = (
  draft: DraftTable,
  rowIndex: number,
  columnIndex: number,
  value: string,
): DraftTable => ({
  ...draft,
  rows: draft.rows.map((row, r) =>
    r === rowIndex
      ? row.map((cell, c) => (c === columnIndex ? { ...cell, value } : cell))
      : row,
  ),
});

export const setColumnLabel = (
  draft: DraftTable,
  columnIndex: number,
  label: string,
): DraftTable => ({
  ...draft,
  columns: draft.columns.map((column, c) =>
    c === columnIndex ? { ...column, label } : column,
  ),
});

export const setColumnAlign = (
  draft: DraftTable,
  columnIndex: number,
  align: ColumnAlign,
): DraftTable => ({
  ...draft,
  columns: draft.columns.map((column, c) =>
    c === columnIndex
      ? { ...column, align, token: retargetAlign(column.token, align) }
      : column,
  ),
});

export const addRow = (draft: DraftTable): DraftTable => ({
  ...draft,
  rows: [...draft.rows, draft.columns.map(() => emptyCell())],
  rowBreaks: [...draft.rowBreaks, ""],
  // Mirror the existing rows' rule so a new row matches (ruled vs borderless).
  rowRules: [
    ...draft.rowRules,
    draft.rowRules[draft.rowRules.length - 1] ?? "",
  ],
});

export const removeRow = (draft: DraftTable, rowIndex: number): DraftTable => ({
  ...draft,
  rows: draft.rows.filter((_, r) => r !== rowIndex),
  rowBreaks: draft.rowBreaks.filter((_, r) => r !== rowIndex),
  rowRules: draft.rowRules.filter((_, r) => r !== rowIndex),
});

const CLINE_RE = /\\cline\s*\{[^}]*\}/g;

/**
 * Column add/remove/move invalidates `\cline{a-b}`'s 1-based column indices;
 * degrade the rule to a full `\hline` (always valid) rather than emit a stale,
 * possibly out-of-range `\cline`.
 */
const degradeRule = (rule: string): string => {
  if (!rule.includes("\\cline")) return rule;
  const tokens = rule
    .split("\n")
    .map((token) => token.replace(CLINE_RE, "\\hline"));
  return [...new Set(tokens)].filter((token) => token !== "").join("\n");
};

const degradeClines = (rules: string[]): string[] => rules.map(degradeRule);

export const addColumn = (draft: DraftTable, atIndex: number): DraftTable => {
  const sibling = draft.columns[Math.max(0, atIndex - 1)] ?? draft.columns[0];
  const column: DraftColumn = {
    label: "",
    align: sibling?.align ?? "left",
    token: defaultColumnToken(sibling?.token ?? null),
    leftBorder: sibling?.leftBorder ?? "",
    template: { kind: "plain" },
    isIdColumn: false,
    headerRaw: null,
  };
  const index = Math.min(Math.max(atIndex, 0), draft.columns.length);
  const columns = [...draft.columns];
  columns.splice(index, 0, column);
  return {
    ...draft,
    columns,
    rowRules: degradeClines(draft.rowRules),
    finalRule: degradeRule(draft.finalRule),
    rows: draft.rows.map((row) => {
      const next = [...row];
      next.splice(index, 0, emptyCell());
      return next;
    }),
  };
};

export const removeColumn = (draft: DraftTable, index: number): DraftTable => {
  const columns = draft.columns.filter((_, c) => c !== index);
  // Deleting column 0 would promote its right-neighbour's separating rule to a
  // spurious outer-left border; drop that now-orphaned border.
  const first = columns[0];
  if (index === 0 && first) columns[0] = { ...first, leftBorder: "" };
  return {
    ...draft,
    columns,
    rowRules: degradeClines(draft.rowRules),
    finalRule: degradeRule(draft.finalRule),
    rows: draft.rows.map((row) => row.filter((_, c) => c !== index)),
  };
};

export const moveColumn = (
  draft: DraftTable,
  from: number,
  to: number,
): DraftTable => {
  if (
    from === to ||
    from < 0 ||
    to < 0 ||
    from >= draft.columns.length ||
    to >= draft.columns.length
  ) {
    return draft;
  }
  const move = <T>(items: T[]): T[] => {
    const next = [...items];
    const [item] = next.splice(from, 1);
    if (item !== undefined) next.splice(to, 0, item);
    return next;
  };
  return {
    ...draft,
    columns: move(draft.columns),
    rowRules: degradeClines(draft.rowRules),
    finalRule: degradeRule(draft.finalRule),
    rows: draft.rows.map((row) => move(row)),
  };
};
