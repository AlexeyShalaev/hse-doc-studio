import { syntaxTree } from "@codemirror/language";
import {
  EditorSelection,
  type ChangeSpec,
  type EditorState,
  type StateCommand,
} from "@codemirror/state";
import type { EditorView } from "@codemirror/view";
import type { SyntaxNode } from "@lezer/common";
import { wrapSelection } from "./commands";
import { collectFillFields, nextField, prevField } from "./visual/fieldNav";
import type { EditorCommandId, EditorFormatState } from "./types";

/**
 * Toolbar / keymap formatting commands. Syntax-tree aware: applying a format
 * inside a matching construct removes it (toggle), otherwise wraps the
 * selection — so they behave sensibly in both code and visual mode.
 */

const editable =
  (command: StateCommand): StateCommand =>
  (target) =>
    target.state.readOnly ? false : command(target);

/** Innermost node from `names` fully covering `[from, to]`. */
const enclosingNode = (
  state: EditorState,
  from: number,
  to: number,
  names: ReadonlySet<string>,
): SyntaxNode | null => {
  for (const side of [-1, 1] as const) {
    let node: SyntaxNode | null = syntaxTree(state).resolveInner(from, side);
    for (; node; node = node.parent) {
      if (names.has(node.name) && node.from <= from && node.to >= to) {
        return node;
      }
    }
  }
  return null;
};

const toggleInlineFormat = (
  nodeNames: string[],
  ctrlSeq: string,
): StateCommand =>
  editable(({ state, dispatch }) => {
    const names = new Set(nodeNames);
    const changes = state.changeByRange((range) => {
      const node = enclosingNode(state, range.from, range.to, names);
      const argument = node?.getChild("TextArgument");
      const open = argument?.getChild("OpenBrace");
      const close = argument?.getChild("CloseBrace");
      if (node && open && close) {
        // Unwrap: drop `\cmd{` and `}`, keep (and select) the body.
        return {
          changes: [
            { from: node.from, to: open.to },
            { from: close.from, to: close.to },
          ],
          range: EditorSelection.range(
            node.from,
            node.from + (close.from - open.to),
          ),
        };
      }
      const selected = state.sliceDoc(range.from, range.to);
      const before = `\\${ctrlSeq}{`;
      return {
        changes: {
          from: range.from,
          to: range.to,
          insert: `${before}${selected}}`,
        },
        range: EditorSelection.range(
          range.from + before.length,
          range.from + before.length + selected.length,
        ),
      };
    });
    dispatch(
      state.update(changes, {
        scrollIntoView: true,
        userEvent: "input.format",
      }),
    );
    return true;
  });

export type HeadingLevelCommand =
  | "chapter"
  | "section"
  | "subsection"
  | "subsubsection";

export const sectioningCommandOnLine = (
  state: EditorState,
  lineFrom: number,
  lineTo: number,
): SyntaxNode | null => {
  let found: SyntaxNode | null = null;
  syntaxTree(state).iterate({
    from: lineFrom,
    to: lineTo,
    enter: (node) => {
      if (found) return false;
      if (node.name === "SectioningCommand") {
        found = node.node;
        return false;
      }
      return undefined;
    },
  });
  return found;
};

const setHeadingLevel = (level: HeadingLevelCommand | null): StateCommand =>
  editable(({ state, dispatch }) => {
    const head = state.selection.main.head;
    const line = state.doc.lineAt(head);
    const command = sectioningCommandOnLine(state, line.from, line.to);
    let changes: ChangeSpec;
    let anchor: number | null = null;

    if (command) {
      const ctrl = command.firstChild;
      const argument = command.getChild("SectioningArgument");
      const open = argument?.getChild("OpenBrace");
      const close = argument?.getChild("CloseBrace");
      if (!ctrl || !open || !close) return false;
      changes =
        level == null
          ? [
              { from: command.from, to: open.to },
              { from: close.from, to: close.to },
            ]
          : // Only the control word changes — `*` and the argument survive.
            { from: ctrl.from, to: ctrl.to, insert: `\\${level}` };
    } else {
      if (level == null) return false;
      const leading = /^\s*/.exec(line.text)?.[0].length ?? 0;
      const contentFrom = line.from + leading;
      if (contentFrom >= line.to) {
        changes = { from: contentFrom, to: line.to, insert: `\\${level}{}` };
        anchor = contentFrom + level.length + 2; // between the braces
      } else {
        changes = [
          { from: contentFrom, insert: `\\${level}{` },
          { from: line.to, insert: "}" },
        ];
      }
    }

    const changeSet = state.changes(changes);
    dispatch(
      state.update({
        changes: changeSet,
        selection: { anchor: anchor ?? changeSet.mapPos(head, 1) },
        scrollIntoView: true,
        userEvent: "input.format",
      }),
    );
    return true;
  });

const LIST_ENV = new Set(["ListEnvironment"]);
const ITEM_PREFIX_RE = /^(\s*)\\item(\[[^\]]*\])? ?/;

const markerAloneOnLine = (state: EditorState, marker: SyntaxNode): boolean => {
  const line = state.doc.lineAt(marker.from);
  return (
    state.doc.sliceString(line.from, marker.from).trim() === "" &&
    state.doc.sliceString(marker.to, line.to).trim() === ""
  );
};

const toggleListEnvironment = (env: "itemize" | "enumerate"): StateCommand =>
  editable(({ state, dispatch }) => {
    const main = state.selection.main;
    const list = enclosingNode(state, main.from, main.to, LIST_ENV);
    const changes: ChangeSpec[] = [];

    if (list) {
      const begin = list.getChild("BeginEnv");
      const end = list.getChild("EndEnv");
      const beginName = begin
        ?.getChild("EnvNameGroup")
        ?.getChild("ListEnvName");
      const endName = end?.getChild("EnvNameGroup")?.getChild("ListEnvName");
      if (!begin || !end || !beginName || !endName) return false;
      const current = state.doc.sliceString(beginName.from, beginName.to);

      if (current !== env) {
        changes.push(
          { from: beginName.from, to: beginName.to, insert: env },
          { from: endName.from, to: endName.to, insert: env },
        );
      } else {
        // Unwrap: remove the markers (whole line when alone) + item prefixes.
        for (const marker of [begin, end]) {
          if (markerAloneOnLine(state, marker)) {
            const line = state.doc.lineAt(marker.from);
            if (line.to < state.doc.length) {
              changes.push({ from: line.from, to: line.to + 1 });
            } else if (line.from > 0) {
              // Last line: swallow the preceding newline instead.
              changes.push({ from: line.from - 1, to: line.to });
            } else {
              changes.push({ from: line.from, to: line.to });
            }
          } else {
            changes.push({ from: marker.from, to: marker.to });
          }
        }
        const firstLine = state.doc.lineAt(begin.to).number + 1;
        const lastLine = state.doc.lineAt(end.from).number - 1;
        for (let n = firstLine; n <= lastLine; n += 1) {
          const line = state.doc.line(n);
          const match = ITEM_PREFIX_RE.exec(line.text);
          if (match) {
            changes.push({
              from: line.from + (match[1]?.length ?? 0),
              to: line.from + match[0].length,
            });
          }
        }
      }
    } else {
      const fromLine = state.doc.lineAt(main.from);
      const toLine = state.doc.lineAt(main.to);
      changes.push({ from: fromLine.from, insert: `\\begin{${env}}\n` });
      for (let n = fromLine.number; n <= toLine.number; n += 1) {
        const line = state.doc.line(n);
        if (line.text.trim() === "") continue;
        const leading = /^\s*/.exec(line.text)?.[0].length ?? 0;
        changes.push({ from: line.from + leading, insert: "\\item " });
      }
      changes.push({ from: toLine.to, insert: `\n\\end{${env}}` });
    }

    const changeSet = state.changes(changes);
    dispatch(
      state.update({
        changes: changeSet,
        selection: { anchor: changeSet.mapPos(main.head, 1) },
        scrollIntoView: true,
        userEvent: "input.format",
      }),
    );
    return true;
  });

type TemplateKind = "inline" | "block";

/**
 * Insert a visual-editor template while keeping the underlying LaTeX fully
 * explicit. The first `\hseFill{…}` placeholder is selected immediately, so
 * the user can start typing and then continue through the remaining fields
 * with Tab. Block templates are moved onto their own lines when invoked in the
 * middle of a paragraph.
 */
const insertTemplate = (
  build: (selected: string) => string,
  kind: TemplateKind,
): StateCommand =>
  editable(({ state, dispatch }) => {
    const changes = state.changeByRange((range) => {
      const selected = state.sliceDoc(range.from, range.to);
      let insert = build(selected);
      let leading = "";

      if (kind === "block") {
        const before =
          range.from > 0 ? state.sliceDoc(range.from - 1, range.from) : "";
        const after =
          range.to < state.doc.length
            ? state.sliceDoc(range.to, range.to + 1)
            : "";
        leading = before && before !== "\n" ? "\n" : "";
        const trailing = after && after !== "\n" ? "\n" : "";
        insert = `${leading}${insert}${trailing}`;
      }

      const fillPrefix = "\\hseFill{";
      const fillStart = insert.indexOf(fillPrefix);
      const fillContentFrom =
        fillStart >= 0 ? fillStart + fillPrefix.length : -1;
      const fillContentTo =
        fillContentFrom >= 0 ? insert.indexOf("}", fillContentFrom) : -1;
      const selectedOffset = selected ? insert.indexOf(selected) : -1;
      const anchorOffset =
        selectedOffset >= 0
          ? selectedOffset
          : fillContentFrom >= 0
            ? fillContentFrom
            : insert.length;
      const headOffset =
        selectedOffset >= 0
          ? selectedOffset + selected.length
          : fillContentTo >= fillContentFrom
            ? fillContentTo
            : anchorOffset;

      return {
        changes: { from: range.from, to: range.to, insert },
        range: EditorSelection.range(
          range.from + anchorOffset,
          range.from + headOffset,
        ),
      };
    });
    dispatch(
      state.update(changes, {
        scrollIntoView: true,
        userEvent: "input.template",
      }),
    );
    return true;
  });

const insertFigure = insertTemplate(
  () =>
    "\\begin{figure}[htbp]\n" +
    "\t\\centering\n" +
    "\t\\includegraphics[width=0.8\\textwidth]{\\hseFill{путь к изображению}}\n" +
    "\t\\caption{\\hseFill{подпись рисунка}}\n" +
    "\t\\label{fig:\\hseFill{метка}}\n" +
    "\\end{figure}",
  "block",
);

const insertTable = insertTemplate(
  () =>
    "\\begin{table}[htbp]\n" +
    "\t\\centering\n" +
    "\t\\caption{\\hseFill{название таблицы}}\n" +
    "\t\\label{tab:\\hseFill{метка}}\n" +
    "\t\\begin{tabular}{|l|l|}\n" +
    "\t\t\\hline\n" +
    "\t\t\\hseFill{заголовок 1} & \\hseFill{заголовок 2} \\\\\n" +
    "\t\t\\hline\n" +
    "\t\t\\hseFill{значение} & \\hseFill{значение} \\\\\n" +
    "\t\t\\hline\n" +
    "\t\\end{tabular}\n" +
    "\\end{table}",
  "block",
);

const insertQuote = insertTemplate(
  (selected) =>
    `\\begin{quote}\n${selected || "\\hseFill{текст цитаты}"}\n\\end{quote}`,
  "block",
);

const insertFootnote = insertTemplate(
  (selected) => `\\footnote{${selected || "\\hseFill{текст сноски}"}}`,
  "inline",
);

const insertCitation = insertTemplate(
  () => "\\cite{\\hseFill{ключ источника}}",
  "inline",
);

const insertPageBreak = insertTemplate(
  (selected) => `\\newpage\n${selected}`,
  "block",
);

const HEADING_COMMANDS = new Set<string>([
  "chapter",
  "section",
  "subsection",
  "subsubsection",
]);

const BOLD_NODES = new Set(["TextBoldCommand"]);
const ITALIC_NODES = new Set(["TextItalicCommand", "EmphasisCommand"]);
const UNDERLINE_NODES = new Set(["UnderlineCommand"]);
const MONO_NODES = new Set(["TextTeletypeCommand"]);

/**
 * Formatting context at the current selection (pure). Powers toolbar active
 * states and the unfilled-fields counter; cheap enough for a throttled
 * update-listener call.
 */
export const selectionFormatState = (state: EditorState): EditorFormatState => {
  const main = state.selection.main;
  const line = state.doc.lineAt(main.head);
  const command = sectioningCommandOnLine(state, line.from, line.to);
  let heading: EditorFormatState["heading"] = null;
  if (command?.firstChild) {
    const name = state.doc
      .sliceString(command.firstChild.from, command.firstChild.to)
      .slice(1);
    if (HEADING_COMMANDS.has(name)) {
      heading = name as Exclude<EditorFormatState["heading"], null>;
    }
  }
  const list = enclosingNode(state, main.from, main.to, LIST_ENV);
  const listName = list
    ?.getChild("BeginEnv")
    ?.getChild("EnvNameGroup")
    ?.getChild("ListEnvName");
  const listKind = listName
    ? state.doc.sliceString(listName.from, listName.to)
    : null;
  return {
    bold: enclosingNode(state, main.from, main.to, BOLD_NODES) != null,
    italic: enclosingNode(state, main.from, main.to, ITALIC_NODES) != null,
    underline:
      enclosingNode(state, main.from, main.to, UNDERLINE_NODES) != null,
    monospace: enclosingNode(state, main.from, main.to, MONO_NODES) != null,
    heading,
    list:
      listKind === "itemize" ||
      listKind === "enumerate" ||
      listKind === "description"
        ? listKind
        : null,
    fieldsRemaining: collectFillFields(state).length,
  };
};

/** Full command registry, keyed by the public string ids (exported for tests). */
export const editorCommands: Record<EditorCommandId, StateCommand> = {
  bold: toggleInlineFormat(["TextBoldCommand"], "textbf"),
  italic: toggleInlineFormat(
    ["TextItalicCommand", "EmphasisCommand"],
    "textit",
  ),
  underline: toggleInlineFormat(["UnderlineCommand"], "underline"),
  monospace: toggleInlineFormat(["TextTeletypeCommand"], "texttt"),
  bulletList: toggleListEnvironment("itemize"),
  numberedList: toggleListEnvironment("enumerate"),
  inlineMath: editable(wrapSelection("$", "$")),
  displayMath: editable(wrapSelection("\\[\n", "\n\\]")),
  "insert:figure": insertFigure,
  "insert:table": insertTable,
  "insert:quote": insertQuote,
  "insert:footnote": insertFootnote,
  "insert:citation": insertCitation,
  "insert:pageBreak": insertPageBreak,
  "heading:chapter": setHeadingLevel("chapter"),
  "heading:section": setHeadingLevel("section"),
  "heading:subsection": setHeadingLevel("subsection"),
  "heading:subsubsection": setHeadingLevel("subsubsection"),
  "heading:none": setHeadingLevel(null),
  nextField,
  prevField,
};

/** ⌘B / ⌘I keymap entries (toggle, replacing the old wrap-only bindings). */
export const toggleBold = editorCommands.bold;
export const toggleItalic = editorCommands.italic;

/** Registry dispatch — the string ids keep CodeMirror types out of features. */
export const runEditorCommand = (
  view: EditorView,
  id: EditorCommandId,
): boolean =>
  editorCommands[id]({ state: view.state, dispatch: view.dispatch.bind(view) });
