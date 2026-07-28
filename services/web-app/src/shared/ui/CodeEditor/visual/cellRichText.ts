/**
 * Conversion between a table cell's inline LaTeX and sanitized HTML for the
 * rich-text cell editor. Only a small, safe inline subset is understood
 * (bold / italic / underline / monospace); everything else degrades to plain
 * text. Nothing here is ever executed as LaTeX or injected as live HTML.
 */

const isControlWordCharacter = (character: string): boolean =>
  /[A-Za-z@]/.test(character);

/** Escape the LaTeX specials a plain-text edit might contain. */
export const escapeLatex = (text: string): string =>
  text.replace(/[\\&%$#_{}~^]/g, (character) => {
    if (character === "\\") return "\\textbackslash{}";
    if (character === "~") return "\\textasciitilde{}";
    if (character === "^") return "\\textasciicircum{}";
    return "\\" + character;
  });

/** A non-breaking space (U+00A0) — what a rendered `~` becomes in the DOM. */
const NBSP = "\u00A0";

/**
 * Escape a run of plain text for inline LaTeX, mapping only a NON-BREAKING
 * space back to `~`. Ordinary spaces stay ordinary spaces (kept explicit as
 * `\u00A0` so the split target can't be silently turned into a normal space).
 */
const escapeLatexKeepingNbsp = (text: string): string =>
  text.split(NBSP).map(escapeLatex).join("~");

const escapeHtml = (text: string): string =>
  text.replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;");

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

const skipWhitespace = (source: string, from: number): number => {
  let cursor = from;
  while (cursor < source.length && /\s/.test(source.charAt(cursor)))
    cursor += 1;
  return cursor;
};

/** Inline formatting commands → HTML tag. */
const WRAP_TAGS: Record<string, string> = {
  textbf: "strong",
  bfseries: "strong",
  textit: "em",
  emph: "em",
  underline: "u",
  texttt: "code",
  textnormal: "span",
  textrm: "span",
  mbox: "span",
};

const SYMBOL: Record<string, string> = {
  ldots: "…",
  dots: "…",
  textellipsis: "…",
  textendash: "–",
  textemdash: "—",
  // Inverses of escapeLatex, so a literal \/~/^ in a cell survives editing.
  textbackslash: "\\",
  textasciitilde: "~",
  textasciicircum: "^",
};

/**
 * Inline LaTeX → sanitized HTML for a contenteditable. Recognized wrappers
 * become tags; `~`→NBSP, `\ldots`→…, `\\`→space, escaped specials→literals,
 * bare braces are transparent, unknown commands are dropped (arguments kept).
 */
export const latexToHtml = (latex: string): string => {
  let html = "";
  const source = latex;
  for (let cursor = 0; cursor < source.length; cursor += 1) {
    const character = source.charAt(cursor);
    if (character === "~") {
      html += " ";
      continue;
    }
    if (character === "{") {
      const group = readGroup(source, cursor);
      if (group) {
        html += latexToHtml(group.content);
        cursor = group.end - 1;
        continue;
      }
      continue;
    }
    if (character === "}") continue;
    if (character !== "\\") {
      html += escapeHtml(character);
      continue;
    }
    const next = source.charAt(cursor + 1);
    if ("&%$#_{}".includes(next)) {
      html += escapeHtml(next);
      cursor += 1;
      continue;
    }
    if (next === "\\") {
      html += " ";
      cursor += 1;
      continue;
    }
    if (next === "~") {
      html += " ";
      cursor += 1;
      continue;
    }
    let end = cursor + 1;
    while (end < source.length && isControlWordCharacter(source.charAt(end))) {
      end += 1;
    }
    const name = source.slice(cursor + 1, end);
    cursor = end - 1;
    const tag = WRAP_TAGS[name];
    if (tag !== undefined) {
      const argument = readGroup(source, skipWhitespace(source, cursor + 1));
      const inner = argument ? latexToHtml(argument.content) : "";
      if (argument) cursor = argument.end - 1;
      html += tag === "span" ? inner : `<${tag}>${inner}</${tag}>`;
      continue;
    }
    const glyph = SYMBOL[name];
    if (glyph !== undefined) {
      html += escapeHtml(glyph);
      continue;
    }
    // Unknown command: drop the control word, keep any following group content.
  }
  return html;
};

/**
 * ALL inline wrappers an element implies, by command. An element can carry
 * several at once (a `<b>` re-styled with underline, or a `<span>` with
 * font-weight+font-style+underline from execCommand); each must be kept and
 * nested, not just the first.
 */
const elementCommands = (element: HTMLElement): string[] => {
  const commands: string[] = [];
  const add = (command: string): void => {
    if (!commands.includes(command)) commands.push(command);
  };
  const tag = element.tagName.toLowerCase();
  if (tag === "b" || tag === "strong") add("textbf");
  if (tag === "i" || tag === "em") add("textit");
  if (tag === "u") add("underline");
  if (tag === "code" || tag === "tt" || tag === "kbd" || tag === "samp")
    add("texttt");
  // execCommand can emit inline styles instead of tags depending on the browser.
  const weight = element.style.fontWeight;
  if (weight === "bold" || weight === "700" || Number(weight) >= 600)
    add("textbf");
  if (element.style.fontStyle === "italic") add("textit");
  const decoration =
    element.style.textDecorationLine || element.style.textDecoration;
  if (decoration.includes("underline")) add("underline");
  return commands;
};

const serializeNode = (node: Node): string => {
  if (node.nodeType === Node.TEXT_NODE) {
    return escapeLatexKeepingNbsp(node.textContent ?? "");
  }
  if (node.nodeType !== Node.ELEMENT_NODE) return "";
  const element = node as HTMLElement;
  const tag = element.tagName.toLowerCase();
  if (tag === "br") return " ";
  const inner = serializeChildren(element);
  if (inner === "") return "";
  const commands = elementCommands(element);
  let out = inner;
  for (const command of [...commands].reverse()) {
    out = `\\${command}{${out}}`;
  }
  // Block elements introduce a soft space so words don't run together.
  if (commands.length === 0 && (tag === "div" || tag === "p")) return `${out} `;
  return out;
};

const serializeChildren = (node: Node): string => {
  let out = "";
  node.childNodes.forEach((child) => {
    out += serializeNode(child);
  });
  return out;
};

/**
 * A contenteditable element's DOM → inline LaTeX. Recognized formatting tags
 * (and equivalent inline styles from `execCommand`) become wrappers; NBSP maps
 * back to `~`, `<br>` and block boundaries to a space.
 */
export const htmlToLatex = (root: Node): string =>
  serializeChildren(root)
    .replace(/[ \t]+/g, " ")
    .trim();
