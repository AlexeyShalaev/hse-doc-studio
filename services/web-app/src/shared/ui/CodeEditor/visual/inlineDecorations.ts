import { syntaxTree } from "@codemirror/language";
import {
  RangeSet,
  type EditorState,
  type Extension,
  type Range,
} from "@codemirror/state";
import {
  Decoration,
  EditorView,
  ViewPlugin,
  type DecorationSet,
  type ViewUpdate,
} from "@codemirror/view";
import type { SyntaxNode } from "@lezer/common";
import { i18n } from "@shared/lib";
import { colorToCss } from "./colors";
import { touchesSelection } from "./reveal";
import { visualConfigFacet, type VisualCallbacks } from "./config";
import {
  ALIGNMENT_ENVS,
  cardEnvironmentKind,
  DECLARATION_COMMANDS,
  DIVIDER_COMMANDS,
  FRAMED_ENVS,
  HEADING_LEVELS,
  INLINE_FORMAT_CLASSES,
  isEmbeddedInput,
  NAMED_PROSE_ENVS,
  PILL_NODES,
  SETUP_CHIP_COMMANDS,
  TEXT_SYMBOL_COMMANDS,
} from "./nodeSets";
import {
  BibFooterWidget,
  BibHeaderWidget,
  BibItemBadgeWidget,
  BulletWidget,
  DividerWidget,
  ImagePreviewWidget,
  InputChipWidget,
  InlineCodeWidget,
  LineBreakWidget,
  MacroFieldWidget,
  ManualDocItemsWidget,
  MathWidget,
  PillWidget,
  PlaceholderFieldWidget,
  SetupChipWidget,
  SlideHeaderWidget,
  SymbolWidget,
} from "./widgets";

/**
 * Layer B of the visual mode: viewport-scoped styling — markup hiding, rich
 * marks (headings, bold/italic), inline widgets (bullets, inline math, pills).
 * Rebuilt on doc/viewport/selection/parse changes; only decorations that never
 * affect vertical layout across lines live here (Layer A handles those).
 */

type Sink = {
  deco: Range<Decoration>[];
  atomics: Range<Decoration>[];
  /** Dedupe guard — a node spanning two visible ranges is entered twice. */
  seen: Set<string>;
  /** Line starts already carrying an env-frame decoration. */
  framedLines: Set<number>;
};

export const createInlineSink = (): Sink => ({
  deco: [],
  atomics: [],
  seen: new Set(),
  framedLines: new Set(),
});

const rangeKey = (prefix: string, from: number, to: number): string =>
  prefix + String(from) + ":" + String(to);

const hide = (sink: Sink, from: number, to: number): void => {
  if (from >= to) return;
  const key = rangeKey("h", from, to);
  if (sink.seen.has(key)) return;
  sink.seen.add(key);
  const replace = Decoration.replace({});
  sink.deco.push(replace.range(from, to));
  sink.atomics.push(replace.range(from, to));
};

const mark = (
  sink: Sink,
  from: number,
  to: number,
  className: string,
): void => {
  if (from >= to) return;
  const key = rangeKey("m", from, to) + ":" + className;
  if (sink.seen.has(key)) return;
  sink.seen.add(key);
  sink.deco.push(Decoration.mark({ class: className }).range(from, to));
};

const widget = (
  sink: Sink,
  from: number,
  to: number,
  w: Decoration,
  key: string,
): void => {
  if (sink.seen.has(key)) return;
  sink.seen.add(key);
  sink.deco.push(w.range(from, to));
  sink.atomics.push(w.range(from, to));
};

const firstDescendant = (node: SyntaxNode, name: string): SyntaxNode | null => {
  let found: SyntaxNode | null = null;
  node.cursor().iterate((n) => {
    if (found) return false;
    if (n.name === name) {
      found = n.node;
      return false;
    }
    return undefined;
  });
  return found;
};

const hasAncestor = (node: SyntaxNode, names: Set<string>): boolean => {
  for (let p = node.parent; p; p = p.parent) {
    if (names.has(p.name)) return true;
  }
  return false;
};

const enclosingList = (node: SyntaxNode): SyntaxNode | null => {
  for (let p = node.parent; p; p = p.parent) {
    if (p.name === "ListEnvironment") return p;
  }
  return null;
};

const listKind = (
  state: EditorState,
  list: SyntaxNode,
): "itemize" | "enumerate" | "description" => {
  const name = list
    .getChild("BeginEnv")
    ?.getChild("EnvNameGroup")
    ?.getChild("ListEnvName");
  const text = name ? state.doc.sliceString(name.from, name.to) : "itemize";
  return text === "enumerate" || text === "description" ? text : "itemize";
};

const listDepth = (list: SyntaxNode): number => {
  let depth = 0;
  for (let p = list.parent; p; p = p.parent) {
    if (p.name === "ListEnvironment") depth += 1;
  }
  return depth;
};

/** 1-based position of the item among its list's direct items. */
const itemIndex = (list: SyntaxNode, itemFrom: number): number => {
  const content = list.getChild("Content");
  if (!content) return 1;
  let count = 0;
  let result = 0;
  content.cursor().iterate((n) => {
    if (result) return false;
    if (n.name === "ListEnvironment") return false; // nested list → own numbering
    if (n.name === "Item") {
      count += 1;
      if (n.from === itemFrom) result = count;
      return false;
    }
    return undefined;
  });
  return result || 1;
};

/** The enclosing `thebibliography` environment node, or null. */
const enclosingBibliography = (
  state: EditorState,
  node: SyntaxNode,
): SyntaxNode | null => {
  for (let p = node.parent; p; p = p.parent) {
    if (p.name !== "Environment") continue;
    const name = p
      .getChild("BeginEnv")
      ?.getChild("EnvNameGroup")
      ?.getChild("EnvName");
    if (
      name &&
      state.doc.sliceString(name.from, name.to) === "thebibliography"
    ) {
      return p;
    }
  }
  return null;
};

/** 1-based position of a `\bibitem` among its bibliography's items. */
const bibitemIndex = (
  state: EditorState,
  bib: SyntaxNode,
  itemFrom: number,
): number => {
  let count = 0;
  let result = 0;
  bib.cursor().iterate((n) => {
    if (result) return false;
    // Don't descend into a nested environment — its \bibitem markers (a nested
    // thebibliography) belong to their own list, not this one's numbering.
    if (n.name === "Environment" && n.from !== bib.from) return false;
    if (n.name !== "UnknownCommand") return undefined;
    const ctrl = n.node.getChild("CtrlSeq");
    if (ctrl && state.doc.sliceString(ctrl.from, ctrl.to) === "\\bibitem") {
      count += 1;
      if (n.from === itemFrom) result = count;
      return false;
    }
    return undefined;
  });
  return result || 1;
};

/** End of the `\begin{thebibliography}{width}` head (past the width group). */
const bibliographyHeadEnd = (state: EditorState, beginTo: number): number => {
  const doc = state.doc;
  let cursor = beginTo;
  const scanLimit = Math.min(doc.length, beginTo + 256);
  while (cursor < scanLimit && /\s/.test(doc.sliceString(cursor, cursor + 1))) {
    cursor += 1;
  }
  if (doc.sliceString(cursor, cursor + 1) !== "{") return beginTo;
  let depth = 0;
  for (let i = cursor; i < Math.min(doc.length, cursor + 256); i += 1) {
    const character = doc.sliceString(i, i + 1);
    if (character === "{") depth += 1;
    else if (character === "}") {
      depth -= 1;
      if (depth === 0) return i + 1;
    }
  }
  return beginTo;
};

const NO_LINEBREAK_GLYPH = new Set([
  "TabularEnvironment",
  "EquationArrayEnvironment",
]);

/**
 * 1-based ordinal of a beamer `\begin{frame}` among the REAL frames before it.
 * Counts `Environment` nodes named `frame` from the syntax tree (not a text
 * regex), so a `\begin{frame}` inside a comment / verbatim / macro body doesn't
 * inflate the slide number.
 */
const frameNumber = (state: EditorState, frameFrom: number): number => {
  let count = 0;
  syntaxTree(state).iterate({
    to: frameFrom,
    enter: (n) => {
      if (n.name !== "Environment" || n.from >= frameFrom) return undefined;
      const name = n.node
        .getChild("BeginEnv")
        ?.getChild("EnvNameGroup")
        ?.getChild("EnvName");
      if (name && state.doc.sliceString(name.from, name.to) === "frame")
        count += 1;
      return undefined;
    },
  });
  return count + 1;
};

/** The title of a beamer `\begin{frame}{Title}` — the last `{…}` arg of its
 *  BeginEnv (which also carries any optional `[overlay]`/`[plain]`). */
const beamerTitle = (
  state: EditorState,
  beginEnv: SyntaxNode | null,
): string => {
  const args = beginEnv?.getChildren("TextArgument") ?? [];
  const last = args.at(-1)?.getChild("LongArg");
  return last ? state.doc.sliceString(last.from, last.to) : "";
};

/**
 * Render one `\item` fragment of an auto-generated doc-list macro to display
 * text: resolve macro references (`\projectname` → `\hseProjectName` → the
 * texesc'd name) against the macro map, un-escape control symbols (`\&` → `&`,
 * so a project name like «R&D» survives), turn `~`/`\ldots` into space/`…`,
 * then drop any still-unknown control word and braces.
 */
const renderDocListItem = (
  raw: string,
  macros: Record<string, string>,
): string => {
  let text = raw;
  for (let pass = 0; pass < 4; pass += 1) {
    const next = text.replace(
      /\\([A-Za-z@]+)/g,
      (full, name: string) => macros[name] ?? full,
    );
    if (next === text) break;
    text = next;
  }
  return text
    .replace(/\\ldots\b|\\dots\b/g, "…")
    .replace(/\\([&%_#{}$])/g, "$1")
    .replace(/\\[A-Za-z@]+\*?/g, "")
    .replace(/~/g, " ")
    .replace(/[{}]/g, "")
    .replace(/\s+/g, " ")
    .trim();
};

/**
 * Pure builder over `[from, to]` (a visible range). Exported for unit tests.
 */
export const buildInlineDecorations = (
  state: EditorState,
  from: number,
  to: number,
  sink: Sink,
  callbacks?: VisualCallbacks,
): void => {
  const doc = state.doc;
  const selection = state.selection;
  const config = state.facet(visualConfigFacet);

  syntaxTree(state).iterate({
    from,
    to,
    enter: (node) => {
      const revealed = touchesSelection(selection, node.from, node.to);

      if (node.name === "SectioningCommand") {
        const parentName = node.node.parent?.name ?? "";
        const level = HEADING_LEVELS[parentName] ?? 2;
        const argument = node.node.getChild("SectioningArgument");
        const openBrace = argument?.getChild("OpenBrace");
        const closeBrace = argument?.getChild("CloseBrace");
        const body = argument?.getChild("LongArg");
        if (!argument || !openBrace || !closeBrace) return;
        const line = doc.lineAt(node.from);
        const lineKey = "l" + String(line.from) + ":heading";
        if (!sink.seen.has(lineKey)) {
          sink.seen.add(lineKey);
          const alignment = config.headingAlignments?.[level];
          sink.deco.push(
            Decoration.line({
              class: alignment
                ? `cm-vis-heading-line cm-vis-align-${alignment}`
                : "cm-vis-heading-line",
            }).range(line.from),
          );
        }
        if (body) {
          mark(
            sink,
            body.from,
            body.to,
            "cm-vis-heading cm-vis-h" + String(level),
          );
        }
        if (!revealed) {
          hide(sink, node.from, openBrace.to);
          hide(sink, closeBrace.from, closeBrace.to);
        }
        return;
      }

      const formatClass = INLINE_FORMAT_CLASSES[node.name];
      if (formatClass) {
        const argument = node.node.getChild("TextArgument");
        const openBrace = argument?.getChild("OpenBrace");
        const closeBrace = argument?.getChild("CloseBrace");
        const body = argument?.getChild("LongArg");
        if (!argument || !openBrace || !closeBrace) return;
        if (body) mark(sink, body.from, body.to, formatClass);
        if (!revealed) {
          hide(sink, node.from, openBrace.to);
          hide(sink, closeBrace.from, closeBrace.to);
        }
        return; // keep descending: nested \textbf{\emph{…}} styles compose
      }

      // `\textcolor{color}{text}` → hide the wrapper and render the text in that
      // color (unknown/xcolor-mix colors fall back to plain text). Descend so
      // nested \textbf/\emph compose.
      if (node.name === "TextColorCommand") {
        const colorArg = node.node
          .getChild("ShortTextArgument")
          ?.getChild("ShortArg");
        const textArg = node.node.getChild("TextArgument");
        const body = textArg?.getChild("LongArg");
        const openBrace = textArg?.getChild("OpenBrace");
        const closeBrace = textArg?.getChild("CloseBrace");
        if (!colorArg || !textArg || !openBrace || !closeBrace) return;
        const css = colorToCss(doc.sliceString(colorArg.from, colorArg.to));
        const colorKey = rangeKey(
          "color",
          body?.from ?? node.from,
          body?.to ?? node.to,
        );
        if (css && body && body.to > body.from && !sink.seen.has(colorKey)) {
          sink.seen.add(colorKey);
          sink.deco.push(
            Decoration.mark({
              attributes: { style: `color:${css}` },
            }).range(body.from, body.to),
          );
        }
        if (!revealed) {
          hide(sink, node.from, openBrace.to);
          hide(sink, closeBrace.from, closeBrace.to);
        }
        return;
      }

      if (node.name === "VerbCommand" || node.name === "LstInlineCommand") {
        if (revealed) return false;
        const content =
          firstDescendant(node.node, "VerbContent") ??
          firstDescendant(node.node, "LstInlineContent");
        if (!content) return;
        widget(
          sink,
          node.from,
          node.to,
          Decoration.replace({
            widget: new InlineCodeWidget(
              doc.sliceString(content.from, content.to),
            ),
          }),
          rangeKey("verb", node.from, node.to),
        );
        return false;
      }

      if (
        node.name === "NewCommand" ||
        node.name === "RenewCommand" ||
        node.name === "SetLengthCommand"
      ) {
        const line = doc.lineAt(node.from);
        const singleLine = line.number === doc.lineAt(node.to).number;
        if (!revealed && singleLine) hide(sink, node.from, node.to);
        return false;
      }

      // `\centering` → hide the token and (safely) center the rest of its
      // enclosing brace group. Scoped to a Group only — never the whole document
      // or a carded figure/table (whose body Layer A already owns).
      if (node.name === "Centering") {
        if (!revealed) hide(sink, node.from, node.to);
        let group: SyntaxNode | null = node.node.parent;
        while (group && group.name !== "Group") group = group.parent;
        if (group) {
          const beginLine = doc.lineAt(node.from);
          const endLine = doc.lineAt(Math.min(group.to, doc.length));
          const firstContent = Math.max(
            beginLine.number,
            doc.lineAt(Math.max(node.from, from)).number,
          );
          const lastContent = Math.min(
            endLine.number,
            doc.lineAt(Math.min(group.to, to)).number,
          );
          for (let n = firstContent; n <= lastContent; n += 1) {
            const cline = doc.line(n);
            if (sink.framedLines.has(cline.from)) continue;
            sink.framedLines.add(cline.from);
            sink.deco.push(
              Decoration.line({ class: "cm-vis-align-center" }).range(
                cline.from,
              ),
            );
          }
        }
        return false;
      }

      if (node.name === "Item") {
        if (revealed) return;
        const list = enclosingList(node.node);
        if (!list) return;
        const kind = listKind(state, list);
        const optional = node.node.getChild("OptionalArgument");
        const label = optional
          ? doc.sliceString(optional.from + 1, optional.to - 1)
          : null;
        widget(
          sink,
          node.from,
          node.to,
          Decoration.replace({
            widget: new BulletWidget(
              kind,
              listDepth(list),
              kind === "enumerate" ? itemIndex(list, node.from) : 0,
              label,
            ),
          }),
          rangeKey("item", node.from, node.to),
        );
        return;
      }

      if (node.name === "Comment") {
        const text = doc.sliceString(node.from, node.to);
        const end = text.endsWith("\n") ? node.to - 1 : node.to;
        mark(sink, node.from, end, "cm-vis-comment");
        return;
      }

      if (node.name === "DollarMath") {
        const inline = node.node.getChild("InlineMath");
        if (!inline) return; // display `$$…$$` → Layer A
        if (doc.sliceString(node.to - 1, node.to) !== "$") return; // unclosed
        if (doc.lineAt(node.from).number !== doc.lineAt(node.to).number) return;
        if (revealed) return false;
        widget(
          sink,
          node.from,
          node.to,
          Decoration.replace({
            widget: new MathWidget(
              doc.sliceString(inline.from, inline.to),
              false,
            ),
          }),
          rangeKey("math", node.from, node.to),
        );
        return false;
      }

      if (node.name === "ParenMath") {
        if (!node.node.getChild("CloseParenMath")) return;
        if (doc.lineAt(node.from).number !== doc.lineAt(node.to).number) return;
        if (revealed) return false;
        const math = node.node.getChild("Math");
        widget(
          sink,
          node.from,
          node.to,
          Decoration.replace({
            widget: new MathWidget(
              math ? doc.sliceString(math.from, math.to) : "",
              false,
            ),
          }),
          rangeKey("math", node.from, node.to),
        );
        return false;
      }

      const pillKind = PILL_NODES[node.name];
      if (pillKind) {
        if (revealed) return false;
        const arg = firstDescendant(node.node, "ShortArg");
        if (!arg) return;
        widget(
          sink,
          node.from,
          node.to,
          Decoration.replace({
            widget: new PillWidget(pillKind, doc.sliceString(arg.from, arg.to)),
          }),
          rangeKey("pill", node.from, node.to),
        );
        return false;
      }

      // `\url{…}` / `\href{url}{label}` → a link pill; `\footnote{…}` → a `†`
      // marker with the note in the tooltip. All dedicated grammar nodes.
      if (node.name === "UrlCommand" || node.name === "HrefCommand") {
        if (revealed) return false;
        const url = firstDescendant(node.node, "LiteralArgContent");
        const label = firstDescendant(node.node, "ShortArg");
        const shown = label ?? url;
        if (!shown) return false;
        const raw = doc.sliceString(shown.from, shown.to);
        // A `\href` label may itself contain markup (\textbf{…}) — show its text.
        const text = raw.includes("\\")
          ? renderDocListItem(raw, config.macros)
          : raw;
        widget(
          sink,
          node.from,
          node.to,
          Decoration.replace({ widget: new PillWidget("link", text) }),
          rangeKey("pill", node.from, node.to),
        );
        return false;
      }

      if (node.name === "FootnoteCommand") {
        if (revealed) return false;
        const body = firstDescendant(node.node, "LongArg");
        widget(
          sink,
          node.from,
          node.to,
          Decoration.replace({
            widget: new PillWidget(
              "note",
              body ? doc.sliceString(body.from, body.to) : "",
            ),
          }),
          rangeKey("pill", node.from, node.to),
        );
        return false;
      }

      if (node.name === "IncludeGraphics") {
        if (revealed) return false;
        const path = firstDescendant(node.node, "LiteralArgContent");
        if (!path) return;
        const file = doc.sliceString(path.from, path.to);
        // Show the real image (Word-style) when the host can resolve a URL
        // for it; otherwise fall back to the filename pill.
        const url = callbacks?.resolveAssetUrl?.(file) ?? null;
        widget(
          sink,
          node.from,
          node.to,
          Decoration.replace({
            widget: url
              ? new ImagePreviewWidget(file, url)
              : new PillWidget("graphic", file.split("/").pop() ?? file),
          }),
          rangeKey("pill", node.from, node.to),
        );
        return false;
      }

      if (node.name === "LineBreak") {
        if (revealed) return;
        if (hasAncestor(node.node, NO_LINEBREAK_GLYPH)) return;
        widget(
          sink,
          node.from,
          node.to,
          Decoration.replace({ widget: new LineBreakWidget() }),
          rangeKey("br", node.from, node.to),
        );
        return;
      }

      if (node.name === "Tilde") {
        if (revealed) return;
        widget(
          sink,
          node.from,
          node.to,
          Decoration.replace({
            widget: new SymbolWidget(" ", "cm-vis-nbsp"),
          }),
          rangeKey("nbsp", node.from, node.to),
        );
        return;
      }

      if (
        node.name === "Input" ||
        node.name === "Include" ||
        node.name === "Subfile"
      ) {
        const path =
          firstDescendant(node.node, "LiteralArgContent") ??
          firstDescendant(node.node, "SpaceDelimitedLiteralArgContent");
        if (!path) return;
        const file = doc.sliceString(path.from, path.to);
        const line = doc.lineAt(node.from);
        const fullLine =
          doc.sliceString(line.from, node.from).trim() === "" &&
          doc.sliceString(node.to, line.to).trim() === "";
        // Layer A owns protected full-line inputs because they change height.
        if (fullLine && isEmbeddedInput(file, config.embeddedInputBasenames)) {
          return false;
        }
        if (revealed) return false;
        widget(
          sink,
          node.from,
          node.to,
          Decoration.replace({
            widget: new InputChipWidget(file, callbacks?.onOpenFile),
          }),
          rangeKey("input", node.from, node.to),
        );
        return false;
      }

      if (node.name === "UnknownCommand") {
        const ctrl = node.node.getChild("CtrlSeq");
        if (!ctrl) return;
        const command = doc.sliceString(ctrl.from, ctrl.to);
        const singleLine =
          doc.lineAt(node.from).number === doc.lineAt(node.to).number;

        if (DIVIDER_COMMANDS.has(command)) {
          if (revealed) return;
          widget(
            sink,
            node.from,
            node.to,
            Decoration.replace({ widget: new DividerWidget(command) }),
            rangeKey("div", node.from, node.to),
          );
          return false;
        }

        // `\bibitem{key}` inside a bibliography → a numbered badge + key chip,
        // leaving the reference text after it as ordinary editable prose.
        if (command === "\\bibitem") {
          const bib = enclosingBibliography(state, node.node);
          if (bib) {
            if (revealed) return; // caret in the marker → reveal to edit the key
            const keyArg = node.node.getChild("TextArgument");
            const keyBody = keyArg?.getChild("LongArg");
            const key = keyBody
              ? doc.sliceString(keyBody.from, keyBody.to).trim()
              : "";
            const replaceEnd = keyArg ? keyArg.to : node.to;
            widget(
              sink,
              node.from,
              replaceEnd,
              Decoration.replace({
                widget: new BibItemBadgeWidget(
                  bibitemIndex(state, bib, node.from),
                  key,
                ),
              }),
              rangeKey("bibitem", node.from, replaceEnd),
            );
            return false;
          }
        }

        // `\newline` → the same ↵ glyph as `\\` (hidden inside tabular/eqnarray).
        if (command === "\\newline") {
          if (revealed) return;
          if (hasAncestor(node.node, NO_LINEBREAK_GLYPH)) {
            hide(sink, node.from, node.to);
            return;
          }
          widget(
            sink,
            node.from,
            node.to,
            Decoration.replace({ widget: new LineBreakWidget() }),
            rangeKey("br", node.from, node.to),
          );
          return false;
        }

        // `\hrulefill` → a stretchy form-blank (a fill-in line, e.g. паспорт …).
        if (command === "\\hrulefill" || command === "\\dotfill") {
          if (revealed) return;
          widget(
            sink,
            node.from,
            node.to,
            Decoration.replace({
              widget: new SymbolWidget("", "cm-vis-formblank"),
            }),
            rangeKey("blank", node.from, node.to),
          );
          return false;
        }

        // `\todo{…}` (todonotes placeholder) → an amber to-do chip; `\reqref{ID}`
        // → a requirement-trace pill. Both carry their argument text.
        if (command === "\\todo" || command === "\\reqref") {
          if (revealed) return;
          const body = node.node.getChild("TextArgument")?.getChild("LongArg");
          const text = body ? doc.sliceString(body.from, body.to) : "";
          widget(
            sink,
            node.from,
            node.to,
            Decoration.replace({
              widget: new PillWidget(
                command === "\\todo" ? "todo" : "req",
                text,
              ),
            }),
            rangeKey("cmdpill", node.from, node.to),
          );
          return false;
        }

        // `\captionof{table}{Text}` (a caption outside a float) → hide the
        // `\captionof{type}{…}` scaffolding and show the text as a caption line.
        if (command === "\\captionof") {
          const args = node.node.getChildren("TextArgument");
          const textArg = args.at(-1);
          const body = textArg?.getChild("LongArg");
          const openBrace = textArg?.getChild("OpenBrace");
          const closeBrace = textArg?.getChild("CloseBrace");
          if (!textArg || !openBrace || !closeBrace) return;
          if (body) mark(sink, body.from, body.to, "cm-vis-caption");
          if (!revealed) {
            hide(sink, node.from, openBrace.to);
            hide(sink, closeBrace.from, closeBrace.to);
          }
          return;
        }

        // `\hseFill{подсказка}` — the pack's yellow "fill me in" placeholder.
        if (command === "\\hseFill") {
          if (revealed || !singleLine) return;
          const body = node.node.getChild("TextArgument")?.getChild("LongArg");
          const hint = body
            ? doc.sliceString(body.from, body.to)
            : command.slice(1);
          widget(
            sink,
            node.from,
            node.to,
            Decoration.replace({
              widget: new PlaceholderFieldWidget(hint, command, true),
            }),
            rangeKey("fill", node.from, node.to),
          );
          return false;
        }

        // Zero-argument macros with a known expansion (project meta) render
        // as Word-style fields showing their value.
        const expansion = config.macros[command.slice(1)];
        if (expansion !== undefined && !node.node.getChild("TextArgument")) {
          if (revealed) return;
          // A macro that expands to `\item`s (the auto-generated manuals list)
          // → a read-only document card, not a raw macro or a flat field.
          if (command === "\\hseManualDocItems") {
            const items = expansion
              .split(/\\item\b/)
              .map((fragment) => renderDocListItem(fragment, config.macros))
              .filter((text) => text !== "");
            if (items.length > 0) {
              widget(
                sink,
                node.from,
                node.to,
                Decoration.replace({ widget: new ManualDocItemsWidget(items) }),
                rangeKey("manuals", node.from, node.to),
              );
              return false;
            }
          }
          const fill = /^\\hseFill\{([\s\S]*)\}$/.exec(expansion);
          const fieldWidget = fill
            ? new PlaceholderFieldWidget(fill[1] ?? "", command, false)
            : expansion === ""
              ? new PlaceholderFieldWidget(command.slice(1), command, false)
              : expansion.includes("\\")
                ? null // complex body — safer to leave the raw macro visible
                : new MacroFieldWidget(command, expansion);
          if (!fieldWidget) return;
          // Replace only the control word, keeping any trailing space.
          widget(
            sink,
            ctrl.from,
            ctrl.to,
            Decoration.replace({ widget: fieldWidget }),
            rangeKey("macro", ctrl.from, ctrl.to),
          );
          return false;
        }

        const symbol = TEXT_SYMBOL_COMMANDS[command];
        if (symbol !== undefined) {
          if (revealed) return;
          widget(
            sink,
            ctrl.from,
            ctrl.to,
            Decoration.replace({
              widget: new SymbolWidget(symbol, "cm-vis-symbol"),
            }),
            rangeKey("sym", ctrl.from, ctrl.to),
          );
          return false;
        }

        if (command in SETUP_CHIP_COMMANDS) {
          if (revealed || !singleLine) return;
          const labelKey = SETUP_CHIP_COMMANDS[command];
          // Pure layout/metadata commands have no printed representation.
          // They should consume no visual space; switch to Code to edit them.
          if (labelKey === null) {
            // A zero-arg declaration: hide ONLY the control word — the grammar
            // greedily attaches a following `[…]`/`{…}` (real visible content,
            // e.g. `\itshape [Схема]`) that must not be swallowed.
            const ctrl = node.node.getChild("CtrlSeq");
            const end =
              DECLARATION_COMMANDS.has(command) && ctrl ? ctrl.to : node.to;
            hide(sink, node.from, end);
            return false;
          }
          const label = labelKey
            ? i18n.t(`codeEditor:visual.${labelKey}`)
            : command.slice(1);
          widget(
            sink,
            node.from,
            node.to,
            Decoration.replace({ widget: new SetupChipWidget(label) }),
            rangeKey("setup", node.from, node.to),
          );
          return false;
        }

        return;
      }

      if (FRAMED_ENVS.has(node.name)) {
        const nameNode = node.node
          .getChild("BeginEnv")
          ?.getChild("EnvNameGroup")
          ?.getChild("EnvName");
        const envName = nameNode
          ? doc.sliceString(nameNode.from, nameNode.to)
          : "";

        // `thebibliography` → a clean list: hide the begin/end markup behind a
        // titled header and a «+ Добавить» footer, then descend so each
        // `\bibitem` becomes a numbered badge and the text stays editable.
        if (node.name === "Environment" && envName === "thebibliography") {
          const onEditBibliography = callbacks?.onEditBibliography;
          const envSource = doc.sliceString(node.from, node.to);
          const beginEnv = node.node.getChild("BeginEnv");
          const endEnv = node.node.getChild("EndEnv");
          const headEnd = bibliographyHeadEnd(
            state,
            beginEnv ? beginEnv.to : node.from,
          );
          if (
            node.from <= to &&
            headEnd >= from &&
            !touchesSelection(selection, node.from, headEnd)
          ) {
            widget(
              sink,
              node.from,
              headEnd,
              Decoration.replace({
                widget: new BibHeaderWidget(envSource, onEditBibliography),
              }),
              rangeKey("bibhead", node.from, headEnd),
            );
          }
          if (
            endEnv &&
            endEnv.from <= to &&
            endEnv.to >= from &&
            !touchesSelection(selection, endEnv.from, endEnv.to)
          ) {
            widget(
              sink,
              endEnv.from,
              endEnv.to,
              Decoration.replace({
                widget: new BibFooterWidget(
                  envSource,
                  endEnv.from - node.from,
                  onEditBibliography,
                ),
              }),
              rangeKey("bibfoot", endEnv.from, endEnv.to),
            );
          }
          return; // descend into the body so \bibitem markers get badged
        }

        // Alignment environments (center/flushleft/flushright): align the
        // content lines (markers hidden by Layer A); the text stays editable.
        const alignment = ALIGNMENT_ENVS[envName];
        if (node.name === "Environment" && alignment) {
          const end = node.node.getChild("EndEnv");
          const beginLine = doc.lineAt(node.from);
          const endLine = doc.lineAt(end ? end.from : node.to);
          const firstContent = Math.max(
            beginLine.number + 1,
            doc.lineAt(Math.max(node.from, from)).number,
          );
          const lastContent = Math.min(
            endLine.number - 1,
            doc.lineAt(Math.min(node.to, to)).number,
          );
          for (let n = firstContent; n <= lastContent; n += 1) {
            const line = doc.line(n);
            if (sink.framedLines.has(line.from)) continue;
            sink.framedLines.add(line.from);
            sink.deco.push(
              Decoration.line({ class: `cm-vis-align-${alignment}` }).range(
                line.from,
              ),
            );
          }
          return; // descend so the content keeps its inline treatment
        }

        // beamer `frame` / `block` → a titled slide/block header; the begin/end
        // markers are hidden and the body stays inline-editable.
        if (
          node.name === "Environment" &&
          (envName === "frame" || envName === "block")
        ) {
          const beginEnv = node.node.getChild("BeginEnv");
          const endEnv = node.node.getChild("EndEnv");
          const headEnd = beginEnv ? beginEnv.to : node.from;
          const title = beamerTitle(state, beginEnv ?? null);
          if (
            node.from <= to &&
            headEnd >= from &&
            !touchesSelection(selection, node.from, headEnd)
          ) {
            const badge =
              envName === "frame"
                ? i18n.t("codeEditor:visual.slideBadge", {
                    n: frameNumber(state, node.from),
                  })
                : i18n.t("codeEditor:visual.blockBadge");
            widget(
              sink,
              node.from,
              headEnd,
              Decoration.replace({
                widget: new SlideHeaderWidget(
                  envName === "frame" ? "🖥" : "▍",
                  renderDocListItem(title, config.macros),
                  badge,
                ),
              }),
              rangeKey("slidehead", node.from, headEnd),
            );
          }
          if (
            endEnv &&
            endEnv.from <= to &&
            endEnv.to >= from &&
            !touchesSelection(selection, endEnv.from, endEnv.to)
          ) {
            hide(sink, endEnv.from, endEnv.to);
          }
          return; // descend so the slide body stays editable
        }

        // beamer `columns` / `column` → just hide the begin/end markers so the
        // nested envs don't stack borders; content stacks vertically.
        if (
          node.name === "Environment" &&
          (envName === "columns" || envName === "column")
        ) {
          const beginEnv = node.node.getChild("BeginEnv");
          const endEnv = node.node.getChild("EndEnv");
          const headEnd = beginEnv ? beginEnv.to : node.from;
          if (
            node.from <= to &&
            headEnd >= from &&
            !touchesSelection(selection, node.from, headEnd)
          ) {
            hide(sink, node.from, headEnd);
          }
          if (
            endEnv &&
            endEnv.from <= to &&
            endEnv.to >= from &&
            !touchesSelection(selection, endEnv.from, endEnv.to)
          ) {
            hide(sink, endEnv.from, endEnv.to);
          }
          return; // descend so the column content stays editable
        }

        // Named prose environments (abstract / keywords / quote…) → a small
        // labelled header; markers hidden, content stays editable.
        const proseLabel = NAMED_PROSE_ENVS[envName];
        if (node.name === "Environment" && proseLabel) {
          const beginEnv = node.node.getChild("BeginEnv");
          const endEnv = node.node.getChild("EndEnv");
          const headEnd = beginEnv ? beginEnv.to : node.from;
          if (
            node.from <= to &&
            headEnd >= from &&
            !touchesSelection(selection, node.from, headEnd)
          ) {
            widget(
              sink,
              node.from,
              headEnd,
              Decoration.replace({
                widget: new SlideHeaderWidget(
                  "§",
                  i18n.t(`codeEditor:visual.env.${proseLabel}`),
                  "",
                ),
              }),
              rangeKey("proselabel", node.from, headEnd),
            );
          }
          if (
            endEnv &&
            endEnv.from <= to &&
            endEnv.to >= from &&
            !touchesSelection(selection, endEnv.from, endEnv.to)
          ) {
            hide(sink, endEnv.from, endEnv.to);
          }
          return; // descend so the content stays editable
        }

        // Configured «образец» environments get tinted content lines instead
        // of the raw frame (banner + hidden end line come from Layer A).
        if (
          node.name === "Environment" &&
          config.highlightEnvs.includes(envName)
        ) {
          const beginLine = doc.lineAt(node.from);
          const end = node.node.getChild("EndEnv");
          const endLine = doc.lineAt(end ? end.from : node.to);
          const firstContent = Math.max(
            beginLine.number + 1,
            doc.lineAt(Math.max(node.from, from)).number,
          );
          const lastContent = Math.min(
            endLine.number - 1,
            doc.lineAt(Math.min(node.to, to)).number,
          );
          for (let n = firstContent; n <= lastContent; n += 1) {
            const line = doc.line(n);
            if (sink.framedLines.has(line.from)) continue;
            sink.framedLines.add(line.from);
            sink.deco.push(
              Decoration.line({ class: "cm-vis-example-line" }).range(
                line.from,
              ),
            );
          }
          return;
        }

        // Structural / code environments render as rich block cards in Layer A
        // (same reveal-to-edit model as formulas): never frame or descend into
        // them here. Only the rare non-full-line env falls back to the frame.
        const beginLine = doc.lineAt(node.from);
        const endLine = doc.lineAt(node.to);
        const fullLine =
          doc.sliceString(beginLine.from, node.from).trim() === "" &&
          doc.sliceString(node.to, endLine.to).trim() === "";
        if (
          fullLine &&
          cardEnvironmentKind(node.name, envName, config.highlightEnvs)
        ) {
          return false;
        }

        const firstLine = doc.lineAt(Math.max(node.from, from));
        const lastLine = doc.lineAt(Math.min(node.to, to));
        for (let n = firstLine.number; n <= lastLine.number; n += 1) {
          const line = doc.line(n);
          if (sink.framedLines.has(line.from)) continue;
          sink.framedLines.add(line.from);
          sink.deco.push(
            Decoration.line({ class: "cm-vis-envframe" }).range(line.from),
          );
        }
        for (const part of ["BeginEnv", "EndEnv"] as const) {
          const marker = node.node.getChild(part);
          if (marker) mark(sink, marker.from, marker.to, "cm-vis-envname");
        }
        return;
      }

      if (node.name === "DocumentEnvironment") {
        const end = node.node.getChild("EndEnv");
        if (end && !touchesSelection(selection, end.from, end.to)) {
          hide(sink, end.from, end.to);
        }
        return;
      }

      return undefined;
    },
  });

  scanDashLigatures(state, from, to, sink);
};

const DASH_RE = /---|--/g;

/**
 * Display-only typographic dashes: `---` → — and `--` → – in prose. The
 * document text never changes; the caret reveals the raw dashes on contact.
 * Only plain `Normal` text qualifies — never math, comments, verbatim,
 * literal arguments or `[--options]` (those tokens aren't `Normal`).
 */
const scanDashLigatures = (
  state: EditorState,
  from: number,
  to: number,
  sink: Sink,
): void => {
  const doc = state.doc;
  const tree = syntaxTree(state);
  const text = doc.sliceString(from, to);
  DASH_RE.lastIndex = 0;
  let match: RegExpExecArray | null;
  while ((match = DASH_RE.exec(text))) {
    const start = from + match.index;
    const end = start + match[0].length;
    if (touchesSelection(state.selection, start, end)) continue;
    const node = tree.resolveInner(start, 1);
    if (node.name !== "Normal") continue;
    if (hasAncestor(node, DASH_EXCLUDED_PARENTS)) continue;
    widget(
      sink,
      start,
      end,
      Decoration.replace({
        widget: new SymbolWidget(
          match[0].length === 3 ? "—" : "–",
          "cm-vis-symbol",
        ),
      }),
      rangeKey("dash", start, end),
    );
  }
};

const DASH_EXCLUDED_PARENTS = new Set([
  "OptionalArgument",
  "Comment",
  "UrlArgument",
  "FilePathArgument",
]);

export const visualViewPlugin = (callbacks?: VisualCallbacks): Extension => {
  class VisualViewPlugin {
    decorations: DecorationSet = Decoration.none;
    atomics: RangeSet<Decoration> = Decoration.none;

    constructor(view: EditorView) {
      this.rebuild(view);
    }

    update(update: ViewUpdate): void {
      if (
        update.docChanged ||
        update.viewportChanged ||
        update.selectionSet ||
        syntaxTree(update.state) !== syntaxTree(update.startState) ||
        // Options (macros, comment visibility) arrive via facet reconfigure.
        update.state.facet(visualConfigFacet) !==
          update.startState.facet(visualConfigFacet)
      ) {
        this.rebuild(update.view);
      }
    }

    private rebuild(view: EditorView): void {
      const sink = createInlineSink();
      for (const range of view.visibleRanges) {
        buildInlineDecorations(
          view.state,
          range.from,
          range.to,
          sink,
          callbacks,
        );
      }
      this.decorations = Decoration.set(sink.deco, true);
      this.atomics = RangeSet.of(sink.atomics, true);
    }
  }

  return ViewPlugin.fromClass(VisualViewPlugin, {
    decorations: (plugin) => plugin.decorations,
    provide: (plugin) =>
      EditorView.atomicRanges.of(
        (view) => view.plugin(plugin)?.atomics ?? RangeSet.empty,
      ),
  });
};

export type { Sink as InlineDecorationSink };
