import { syntaxTree } from "@codemirror/language";
import { WidgetType, type EditorView } from "@codemirror/view";
import type { SyntaxNode } from "@lezer/common";
import { i18n } from "@shared/lib";
import { parseChangeLogPreview } from "./changeLogPreview";
import { parseEditableTable } from "./editableTable";
import { parseFigurePreview } from "./figurePreview";
import { parseGenericInputPreview } from "./genericInputPreview";
import { renderMathInto } from "./katexRenderer";
import { setPreambleCollapsed } from "./effects";
import { insideSelection } from "./reveal";
import { parseRequirementsTablePreview } from "./requirementsTablePreview";
import { parseTablePreview } from "./tablePreview";
import { buildTitlePreview } from "./titlePreview";

const addKeyboardActivation = (
  dom: HTMLElement,
  activate: () => void,
  label?: string,
): void => {
  dom.setAttribute("role", "button");
  dom.tabIndex = 0;
  dom.setAttribute(
    "aria-label",
    label ?? i18n.t("codeEditor:visual.editSource"),
  );
  dom.addEventListener("keydown", (event) => {
    if (event.key !== "Enter" && event.key !== " ") return;
    event.preventDefault();
    event.stopPropagation();
    activate();
  });
};

/**
 * Place the cursor at the widget's current document position, revealing the
 * construct it replaces. Resolved at click time via `posAtDOM` — never from a
 * position captured at build time, which goes stale across edits while `eq()`
 * keeps the DOM alive.
 */
const revealOnMouseDown = (
  dom: HTMLElement,
  view: EditorView,
  keyboardAccessible = false,
): void => {
  const reveal = (): void => {
    const pos = view.posAtDOM(dom);
    view.dispatch({ selection: { anchor: pos }, scrollIntoView: true });
    view.focus();
  };
  dom.addEventListener("mousedown", (event) => {
    if (event.button !== 0 || event.ctrlKey || event.metaKey) return;
    event.preventDefault();
    reveal();
  });
  if (keyboardAccessible) addKeyboardActivation(dom, reveal, dom.title);
};

/**
 * Click on a template field → select the whole underlying macro so the first
 * keystroke replaces it (Word content-control behavior). The node is resolved
 * at click time; `length` is the fallback when the widget replaces a known
 * span (a bare control word) rather than a full command node.
 */
const selectFieldOnMouseDown = (
  dom: HTMLElement,
  view: EditorView,
  wholeCommand: boolean,
  length: number,
): void => {
  const selectField = (): void => {
    const pos = view.posAtDOM(dom);
    let anchor = pos;
    let head = Math.min(pos + length, view.state.doc.length);
    if (wholeCommand) {
      let node: SyntaxNode | null = syntaxTree(view.state).resolveInner(pos, 1);
      for (; node; node = node.parent) {
        if (node.name === "UnknownCommand") {
          anchor = node.from;
          head = node.to;
          break;
        }
      }
    }
    view.dispatch({ selection: { anchor, head }, scrollIntoView: true });
    view.focus();
  };
  dom.addEventListener("mousedown", (event) => {
    if (event.button !== 0 || event.ctrlKey || event.metaKey) return;
    event.preventDefault();
    selectField();
  });
  addKeyboardActivation(dom, selectField, dom.title);
};

const BULLETS = ["•", "◦", "▪"];

/** Replaces `\item ` with a list bullet / number / description term. */
export class BulletWidget extends WidgetType {
  constructor(
    readonly kind: "itemize" | "enumerate" | "description",
    readonly depth: number,
    readonly index: number,
    readonly label: string | null,
  ) {
    super();
  }

  override eq(other: BulletWidget): boolean {
    return (
      other.kind === this.kind &&
      other.depth === this.depth &&
      other.index === this.index &&
      other.label === this.label
    );
  }

  toDOM(view: EditorView): HTMLElement {
    const span = document.createElement("span");
    span.className = `cm-vis-bullet cm-vis-bullet-${this.kind}`;
    if (this.kind === "enumerate") {
      span.textContent = String(this.index) + ".";
    } else if (this.kind === "description") {
      span.textContent = this.label ?? "•";
      span.classList.add("cm-vis-b");
    } else {
      span.textContent =
        BULLETS[Math.min(this.depth, BULLETS.length - 1)] ?? "•";
    }
    revealOnMouseDown(span, view);
    return span;
  }

  override ignoreEvent(): boolean {
    return true;
  }
}

/** Collapsed preamble → one banner line; click expands to the raw source. */
export class PreambleWidget extends WidgetType {
  constructor(readonly lineCount: number) {
    super();
  }

  override eq(other: PreambleWidget): boolean {
    return other.lineCount === this.lineCount;
  }

  toDOM(view: EditorView): HTMLElement {
    const banner = document.createElement("div");
    banner.className = "cm-vis-preamble";
    banner.title = i18n.t("codeEditor:visual.preambleExpand");
    const chevron = document.createElement("span");
    chevron.className = "cm-vis-preamble-chevron";
    chevron.textContent = "▸";
    const label = document.createElement("span");
    label.textContent = `${i18n.t("codeEditor:visual.preamble")} · ${i18n.t(
      "codeEditor:visual.preambleLines",
      { count: this.lineCount },
    )}`;
    banner.append(chevron, label);
    const expand = (): void => {
      view.dispatch({ effects: setPreambleCollapsed.of(false) });
      view.focus();
    };
    banner.addEventListener("mousedown", (event) => {
      event.preventDefault();
      expand();
    });
    addKeyboardActivation(banner, expand, banner.title);
    return banner;
  }

  override ignoreEvent(): boolean {
    return true;
  }
}

/** Chip above an expanded preamble offering to collapse it again. */
export class PreambleCollapseWidget extends WidgetType {
  override eq(): boolean {
    return true;
  }

  toDOM(view: EditorView): HTMLElement {
    const banner = document.createElement("div");
    banner.className = "cm-vis-preamble cm-vis-preamble-open";
    const chevron = document.createElement("span");
    chevron.className = "cm-vis-preamble-chevron";
    chevron.textContent = "▾";
    const label = document.createElement("span");
    label.textContent = i18n.t("codeEditor:visual.preambleCollapse");
    banner.append(chevron, label);
    const collapse = (): void => {
      // A caret still inside the preamble would keep it revealed and make
      // the collapse a visual no-op — move the selection just past it first.
      const end = preambleEndAt(view);
      const inside = end >= 0 && insideSelection(view.state.selection, 0, end);
      view.dispatch({
        effects: setPreambleCollapsed.of(true),
        ...(inside
          ? {
              selection: {
                anchor: Math.min(end + 1, view.state.doc.length),
              },
            }
          : {}),
      });
      view.focus();
    };
    banner.addEventListener("mousedown", (event) => {
      event.preventDefault();
      collapse();
    });
    addKeyboardActivation(
      banner,
      collapse,
      i18n.t("codeEditor:visual.preambleCollapse"),
    );
    return banner;
  }

  override ignoreEvent(): boolean {
    return true;
  }
}

/** End of the `\begin{document}` line, resolved at event time (-1 = none). */
export const preambleEndAt = (view: EditorView): number => {
  let end = -1;
  syntaxTree(view.state).iterate({
    enter: (node) => {
      if (end >= 0) return false;
      if (node.name === "DocumentEnvironment") {
        const begin = node.node.getChild("BeginEnv");
        if (begin) end = view.state.doc.lineAt(begin.from).to;
        return false;
      }
      return undefined;
    },
  });
  return end;
};

/**
 * Inline or display formula rendered with KaTeX. The raw source shows as a
 * mono placeholder until the (lazily loaded) renderer resolves; a hard render
 * failure keeps the raw source in the error style. Click → edit the source.
 */
export class MathWidget extends WidgetType {
  constructor(
    readonly tex: string,
    readonly display: boolean,
  ) {
    super();
  }

  override eq(other: MathWidget): boolean {
    return other.tex === this.tex && other.display === this.display;
  }

  toDOM(view: EditorView): HTMLElement {
    const el = document.createElement(this.display ? "div" : "span");
    el.className = this.display
      ? "cm-vis-math cm-vis-math-display cm-vis-math-pending"
      : "cm-vis-math cm-vis-math-pending";
    el.textContent = this.tex;
    renderMathInto(el, this.tex, this.display);
    revealOnMouseDown(el, view, true);
    return el;
  }

  override ignoreEvent(): boolean {
    return true;
  }
}

/**
 * `\ref` / `\cite` / `\label` / `\includegraphics` and friends drawn as a
 * compact pill. `link` = `\url`/`\href`, `req` = `\reqref`, `todo` = `\todo`
 * (an amber "to-do" chip), `note` = `\footnote` (a `†` marker with the note in
 * the tooltip). Click reveals the raw command.
 */
export class PillWidget extends WidgetType {
  constructor(
    readonly kind:
      | "ref"
      | "cite"
      | "label"
      | "graphic"
      | "link"
      | "req"
      | "todo"
      | "note",
    readonly text: string,
  ) {
    super();
  }

  override eq(other: PillWidget): boolean {
    return other.kind === this.kind && other.text === this.text;
  }

  toDOM(view: EditorView): HTMLElement {
    const span = document.createElement("span");
    span.className = `cm-vis-pill cm-vis-pill-${this.kind}`;
    if (this.kind === "note") {
      // A footnote prints as a superscript mark, not the whole note inline.
      span.textContent = "†";
      span.title = this.text;
    } else {
      const PREFIX: Record<Exclude<PillWidget["kind"], "note">, string> = {
        ref: "→ ",
        cite: "[¶] ",
        label: "⌖ ",
        graphic: "🖼 ",
        link: "🔗 ",
        req: "⛓ ",
        todo: "⚠ ",
      };
      span.textContent = `${PREFIX[this.kind]}${this.text}`;
      span.title = i18n.t(`codeEditor:visual.pill.${this.kind}`, {
        target: this.text,
      });
    }
    revealOnMouseDown(span, view, true);
    return span;
  }

  override ignoreEvent(): boolean {
    return true;
  }
}

/** Inline `\verb|...|` / `\lstinline|...|` rendered as inert code text. */
export class InlineCodeWidget extends WidgetType {
  constructor(readonly text: string) {
    super();
  }

  override eq(other: InlineCodeWidget): boolean {
    return other.text === this.text;
  }

  toDOM(view: EditorView): HTMLElement {
    const code = document.createElement("code");
    code.className = "cm-vis-inline-code";
    code.textContent = this.text;
    code.title = i18n.t("codeEditor:visual.inlineCodeSource");
    revealOnMouseDown(code, view, true);
    return code;
  }

  override ignoreEvent(): boolean {
    return true;
  }
}

/**
 * Inline preview of `\includegraphics{…}` — the actual image, Word-style.
 * Constant-height box so async image loading never shifts the layout;
 * a load failure switches to a broken-file note inside the same box.
 */
export class ImagePreviewWidget extends WidgetType {
  constructor(
    readonly file: string,
    readonly url: string,
  ) {
    super();
  }

  override eq(other: ImagePreviewWidget): boolean {
    return other.file === this.file && other.url === this.url;
  }

  override get estimatedHeight(): number {
    return 188;
  }

  toDOM(view: EditorView): HTMLElement {
    const wrap = document.createElement("span");
    wrap.className = "cm-vis-img";
    const img = document.createElement("img");
    img.src = this.url;
    img.alt = this.file;
    img.loading = "lazy";
    img.draggable = false;
    const name = document.createElement("span");
    name.className = "cm-vis-img-name";
    name.textContent = this.file.split("/").pop() ?? this.file;
    img.addEventListener("error", () => {
      wrap.classList.add("cm-vis-img-broken");
      name.textContent = `⚠ ${this.file}`;
    });
    wrap.append(img, name);
    revealOnMouseDown(wrap, view, true);
    return wrap;
  }

  override ignoreEvent(): boolean {
    return true;
  }
}

/**
 * The `\begin{frame}{Title}` / `\begin{block}{Title}` line of a beamer slide,
 * shown as a titled header (icon + title + a «Слайд N» / «Блок» badge) instead
 * of raw markup. The body stays inline-editable; click reveals the raw source.
 */
export class SlideHeaderWidget extends WidgetType {
  constructor(
    readonly icon: string,
    readonly title: string,
    readonly badge: string,
  ) {
    super();
  }

  override eq(other: SlideHeaderWidget): boolean {
    return (
      other.icon === this.icon &&
      other.title === this.title &&
      other.badge === this.badge
    );
  }

  toDOM(view: EditorView): HTMLElement {
    const root = document.createElement("span");
    root.className = "cm-vis-slide-head";
    const icon = document.createElement("span");
    icon.className = "cm-vis-slide-icon";
    icon.textContent = this.icon;
    const title = document.createElement("span");
    title.className = "cm-vis-slide-title";
    title.textContent = this.title;
    root.append(icon, title);
    if (this.badge !== "") {
      const badge = document.createElement("span");
      badge.className = "cm-vis-slide-badge";
      badge.textContent = this.badge;
      root.append(badge);
    }
    revealOnMouseDown(root, view);
    return root;
  }

  override ignoreEvent(): boolean {
    return true;
  }
}

/** `\newpage`-style commands drawn as a labelled horizontal divider. */
export class DividerWidget extends WidgetType {
  constructor(readonly command: string) {
    super();
  }

  override eq(other: DividerWidget): boolean {
    return other.command === this.command;
  }

  toDOM(view: EditorView): HTMLElement {
    const span = document.createElement("span");
    span.className = "cm-vis-divider";
    const label = document.createElement("span");
    label.className = "cm-vis-divider-label";
    label.textContent = i18n.t("codeEditor:visual.pageBreak");
    span.appendChild(label);
    revealOnMouseDown(span, view, true);
    return span;
  }

  override ignoreEvent(): boolean {
    return true;
  }
}

/**
 * A zero-argument macro rendered as a Word-style field showing its resolved
 * value (`\hseProjectName` → «Ядро …»). Click → edit the raw macro.
 */
export class MacroFieldWidget extends WidgetType {
  constructor(
    readonly name: string,
    readonly value: string,
  ) {
    super();
  }

  override eq(other: MacroFieldWidget): boolean {
    return other.name === this.name && other.value === this.value;
  }

  toDOM(view: EditorView): HTMLElement {
    const span = document.createElement("span");
    span.className = "cm-vis-field";
    span.textContent = this.value;
    span.title = this.name;
    revealOnMouseDown(span, view, true);
    return span;
  }

  override ignoreEvent(): boolean {
    return true;
  }
}

/**
 * A macro that expands to an auto-generated list of documents (e.g.
 * `\hseManualDocItems` → the manuals in the set) rendered as a read-only card:
 * you don't edit the list here, you change the setting that drives it. Click
 * reveals the raw macro.
 */
export class ManualDocItemsWidget extends WidgetType {
  constructor(readonly items: readonly string[]) {
    super();
  }

  override eq(other: ManualDocItemsWidget): boolean {
    return (
      other.items.length === this.items.length &&
      other.items.every((value, index) => value === this.items[index])
    );
  }

  toDOM(view: EditorView): HTMLElement {
    const root = document.createElement("span");
    root.className = "cm-vis-manuals";
    root.title = i18n.t("codeEditor:visual.manualsHint");
    const badge = document.createElement("span");
    badge.className = "cm-vis-manuals-badge";
    badge.textContent = i18n.t("codeEditor:visual.manualsBadge");
    root.append(badge);
    const list = document.createElement("span");
    list.className = "cm-vis-manuals-list";
    for (const item of this.items) {
      const row = document.createElement("span");
      row.className = "cm-vis-manuals-item";
      const icon = document.createElement("span");
      icon.className = "cm-vis-manuals-icon";
      icon.textContent = "📄";
      const text = document.createElement("span");
      text.className = "cm-vis-manuals-text";
      text.textContent = item;
      row.append(icon, text);
      list.append(row);
    }
    root.append(list);
    revealOnMouseDown(root, view);
    return root;
  }

  override ignoreEvent(): boolean {
    return true;
  }
}

/**
 * An unfilled `\hseFill{hint}` placeholder — mirrors the yellow «заполните
 * сами» boxes the pack prints in the PDF. Click selects the whole macro so
 * typing immediately replaces it with the student's own text.
 */
export class PlaceholderFieldWidget extends WidgetType {
  constructor(
    readonly hint: string,
    readonly name: string,
    /** true → widget replaces a whole `\hseFill{…}` command node. */
    readonly wholeCommand: boolean,
  ) {
    super();
  }

  override eq(other: PlaceholderFieldWidget): boolean {
    return (
      other.hint === this.hint &&
      other.name === this.name &&
      other.wholeCommand === this.wholeCommand
    );
  }

  toDOM(view: EditorView): HTMLElement {
    const span = document.createElement("span");
    span.className = "cm-vis-fill";
    span.textContent = `⟨${this.hint}⟩`;
    span.title = `${this.name} — ${i18n.t("codeEditor:visual.fillTitle")}`;
    selectFieldOnMouseDown(span, view, this.wholeCommand, this.name.length);
    return span;
  }

  override ignoreEvent(): boolean {
    return true;
  }
}

/**
 * A run of «% Подсказка: …» comments rendered as a readable callout — the
 * pack's scaffolding guidance, visible instead of buried in a chip. Body
 * click reveals the raw comments for editing; ✕ deletes the whole hint.
 */
export class HintCalloutWidget extends WidgetType {
  constructor(readonly text: string) {
    super();
  }

  override eq(other: HintCalloutWidget): boolean {
    return other.text === this.text;
  }

  toDOM(view: EditorView): HTMLElement {
    const el = document.createElement("div");
    el.className = "cm-vis-hint";
    const icon = document.createElement("span");
    icon.className = "cm-vis-hint-icon";
    icon.textContent = "💡";
    const body = document.createElement("span");
    body.className = "cm-vis-hint-text";
    body.textContent = this.text;
    const close = document.createElement("button");
    close.type = "button";
    close.className = "cm-vis-hint-close";
    close.textContent = "✕";
    close.title = i18n.t("codeEditor:visual.hintDelete");
    close.setAttribute("aria-label", i18n.t("codeEditor:visual.hintDelete"));
    el.append(icon, body, close);
    revealOnMouseDown(el, view);
    close.addEventListener("mousedown", (event) => {
      // Read-only editors must not mutate; fall through to the body's
      // reveal behavior instead (readOnly is checked at event time — the
      // compartment can reconfigure while eq() keeps this DOM alive).
      if (view.state.readOnly) return;
      event.preventDefault();
      event.stopPropagation();
    });
    close.addEventListener("click", (event) => {
      if (view.state.readOnly) return;
      // Delete the whole comment run (resolved at click time, not build time).
      event.preventDefault();
      event.stopPropagation();
      const pos = view.posAtDOM(el);
      const doc = view.state.doc;
      let line = doc.lineAt(pos);
      const from = line.from;
      let to = line.to;
      while (line.number < doc.lines) {
        const next = doc.line(line.number + 1);
        if (!/^\s*%/.test(next.text)) break;
        line = next;
        to = next.to;
      }
      view.dispatch({
        changes: { from, to: Math.min(to + 1, doc.length) },
        userEvent: "delete",
      });
      view.focus();
    });
    return el;
  }

  override ignoreEvent(): boolean {
    return true;
  }
}

/** Banner replacing the `\begin{…}` line of a highlighted «образец» block. */
export class BannerWidget extends WidgetType {
  override eq(): boolean {
    return true;
  }

  toDOM(view: EditorView): HTMLElement {
    const el = document.createElement("div");
    el.className = "cm-vis-example-banner";
    el.textContent = `⚠ ${i18n.t("codeEditor:visual.exampleBanner")}`;
    revealOnMouseDown(el, view);
    return el;
  }

  override ignoreEvent(): boolean {
    return true;
  }
}

/** A no-prose setup command (`\addcontentsline`, `\medskip`…) as a tiny chip. */
export class SetupChipWidget extends WidgetType {
  constructor(readonly label: string) {
    super();
  }

  override eq(other: SetupChipWidget): boolean {
    return other.label === this.label;
  }

  toDOM(view: EditorView): HTMLElement {
    const span = document.createElement("span");
    span.className = "cm-vis-setup";
    span.textContent = this.label;
    revealOnMouseDown(span, view, true);
    return span;
  }

  override ignoreEvent(): boolean {
    return true;
  }
}

/**
 * `\input{file}` / `\include{file}` as a file-reference chip. Click opens the
 * referenced file (when the host wires `onOpenFile`); Alt+click reveals the
 * raw command for editing.
 */
export class InputChipWidget extends WidgetType {
  constructor(
    readonly path: string,
    readonly onOpenFile?: (path: string) => void,
  ) {
    super();
  }

  override eq(other: InputChipWidget): boolean {
    // The callback is a stable ref-reading wrapper — compare presence only.
    return (
      other.path === this.path &&
      Boolean(other.onOpenFile) === Boolean(this.onOpenFile)
    );
  }

  toDOM(view: EditorView): HTMLElement {
    const span = document.createElement("span");
    span.className = "cm-vis-pill cm-vis-pill-input";
    span.textContent = `⤷ ${this.path.split("/").pop() ?? this.path}`;
    span.title = this.onOpenFile
      ? i18n.t("codeEditor:visual.inputOpen", { file: this.path })
      : this.path;
    const reveal = (): void => {
      const pos = view.posAtDOM(span);
      view.dispatch({ selection: { anchor: pos }, scrollIntoView: true });
      view.focus();
    };
    const open = (): void => {
      if (this.onOpenFile) this.onOpenFile(this.path);
      else reveal();
    };
    span.addEventListener("mousedown", (event) => {
      if (event.button !== 0 || event.ctrlKey || event.metaKey) return;
      event.preventDefault();
      if (this.onOpenFile && !event.altKey) {
        open();
        return;
      }
      // Alt+click (or no handler) → reveal the raw command for editing.
      reveal();
    });
    addKeyboardActivation(span, open, span.title);
    return span;
  }

  override ignoreEvent(): boolean {
    return true;
  }
}

/** Honest source-backed fallback for a direct input without a specialist IR. */
export class EmbeddedInputBlockWidget extends WidgetType {
  constructor(
    readonly path: string,
    readonly source: string | undefined,
    readonly onOpenFile?: (path: string) => void,
  ) {
    super();
  }

  override eq(other: EmbeddedInputBlockWidget): boolean {
    return (
      other.path === this.path &&
      other.source === this.source &&
      Boolean(other.onOpenFile) === Boolean(this.onOpenFile)
    );
  }

  override get estimatedHeight(): number {
    const count = parseGenericInputPreview(this.source).snippets.length;
    return 150 + Math.max(1, count) * 38;
  }

  toDOM(): HTMLElement {
    const preview = parseGenericInputPreview(this.source);
    const root = document.createElement("section");
    root.className = "cm-vis-source-block cm-vis-generic-input";
    root.setAttribute("role", "group");
    root.setAttribute(
      "aria-label",
      i18n.t("codeEditor:visual.genericInputLabel", {
        file: this.path.split("/").pop() ?? this.path,
      }),
    );
    root.append(
      createSourceBlockToolbar({
        path: this.path,
        label: i18n.t("codeEditor:visual.genericInputLabel", {
          file: this.path.split("/").pop() ?? this.path,
        }),
        description: i18n.t("codeEditor:visual.genericInputDescription", {
          lines: preview.lineCount,
          sections: preview.sectionCount,
          tables: preview.tableCount,
          lists: preview.listCount,
        }),
        status: i18n.t("codeEditor:visual.requirementsProtected"),
        openLabel: i18n.t("codeEditor:visual.sourceOpen"),
        onOpenFile: this.onOpenFile,
      }),
    );
    const notice = document.createElement("div");
    notice.className = "cm-vis-source-notice";
    notice.textContent = i18n.t(
      this.source === undefined
        ? "codeEditor:visual.inputLoading"
        : "codeEditor:visual.genericInputNotice",
    );
    const snippets = document.createElement("div");
    snippets.className = "cm-vis-generic-snippets";
    for (const text of preview.snippets) {
      appendText(snippets, "cm-vis-generic-snippet", text);
    }
    if (preview.snippets.length === 0 && this.source !== undefined) {
      appendText(
        snippets,
        "cm-vis-generic-empty",
        i18n.t("codeEditor:visual.genericInputEmpty"),
      );
    }
    root.append(notice, snippets);
    return root;
  }

  override ignoreEvent(): boolean {
    return true;
  }
}

type SourceBlockToolbarOptions = {
  path: string;
  label: string;
  description: string;
  status: string;
  openLabel: string;
  onOpenFile: ((path: string) => void) | undefined;
};

const createSourceBlockToolbar = ({
  path,
  label,
  description,
  status,
  openLabel,
  onOpenFile,
}: SourceBlockToolbarOptions): HTMLElement => {
  const toolbar = document.createElement("header");
  toolbar.className = "cm-vis-source-toolbar";
  const copy = document.createElement("span");
  copy.className = "cm-vis-source-copy";
  const title = document.createElement("strong");
  title.textContent = label;
  const details = document.createElement("span");
  details.textContent = description;
  const source = document.createElement("code");
  source.textContent = path.split("/").pop() ?? path;
  copy.append(title, details, source);

  const protection = document.createElement("span");
  protection.className = "cm-vis-source-status";
  protection.textContent = status;
  toolbar.append(copy, protection);

  if (onOpenFile) {
    const open = document.createElement("button");
    open.type = "button";
    open.className = "cm-vis-source-open";
    open.textContent = openLabel;
    open.addEventListener("mousedown", (event) => {
      event.preventDefault();
      event.stopPropagation();
    });
    open.addEventListener("click", (event) => {
      event.preventDefault();
      event.stopPropagation();
      onOpenFile(path);
    });
    toolbar.append(open);
  }
  return toolbar;
};

const appendText = (
  parent: HTMLElement,
  className: string,
  text: string,
): HTMLElement => {
  const element = document.createElement("div");
  element.className = className;
  element.textContent = text;
  parent.append(element);
  return element;
};

/** Source-backed ESPD (two pages) or VКР (one page) title preview. */
export class TitleInputBlockWidget extends WidgetType {
  constructor(
    readonly path: string,
    readonly source: string | undefined,
    readonly variant: "titlePages" | "vkrTitle",
    readonly macros: Readonly<Record<string, string>>,
    readonly onOpenFile?: (path: string) => void,
  ) {
    super();
  }

  override eq(other: TitleInputBlockWidget): boolean {
    return (
      other.path === this.path &&
      other.source === this.source &&
      other.variant === this.variant &&
      other.macros === this.macros &&
      Boolean(other.onOpenFile) === Boolean(this.onOpenFile)
    );
  }

  override get estimatedHeight(): number {
    return this.variant === "titlePages" ? 610 : 760;
  }

  toDOM(): HTMLElement {
    const preview = buildTitlePreview(this.variant, this.macros, this.source);
    const isEspd = preview.kind === "titlePages";
    const root = document.createElement("section");
    root.className = `cm-vis-source-block cm-vis-title-block ${
      isEspd ? "is-espd" : "is-vkr"
    }`;
    root.setAttribute("role", "group");
    root.setAttribute(
      "aria-label",
      i18n.t(
        isEspd
          ? "codeEditor:visual.titleEspdLabel"
          : "codeEditor:visual.titleVkrLabel",
      ),
    );
    root.append(
      createSourceBlockToolbar({
        path: this.path,
        label: i18n.t(
          isEspd
            ? "codeEditor:visual.titleEspdLabel"
            : "codeEditor:visual.titleVkrLabel",
        ),
        description: i18n.t(
          isEspd
            ? "codeEditor:visual.titleEspdDescription"
            : "codeEditor:visual.titleVkrDescription",
          { count: preview.sourceLineCount ?? "…" },
        ),
        status: i18n.t("codeEditor:visual.embeddedProtected"),
        openLabel: i18n.t("codeEditor:visual.embeddedOpen"),
        onOpenFile: this.onOpenFile,
      }),
    );

    const notice = document.createElement("div");
    notice.className = "cm-vis-source-notice";
    notice.textContent = i18n.t("codeEditor:visual.structuralPreviewNotice");
    root.append(notice);

    const pages = document.createElement("div");
    pages.className = "cm-vis-title-pages";
    if (preview.kind === "titlePages") {
      const approval = document.createElement("article");
      approval.className = "cm-vis-title-page cm-vis-title-approval";
      approval.setAttribute(
        "aria-label",
        i18n.t("codeEditor:visual.approvalSheet"),
      );
      appendText(
        approval,
        "cm-vis-title-page-badge",
        i18n.t("codeEditor:visual.approvalSheet"),
      );
      appendText(
        approval,
        "cm-vis-title-institution",
        "ПРАВИТЕЛЬСТВО РОССИЙСКОЙ ФЕДЕРАЦИИ\nНИУ «ВЫСШАЯ ШКОЛА ЭКОНОМИКИ»\nФакультет компьютерных наук\nОП «Программная инженерия»",
      );
      const approvals = document.createElement("div");
      approvals.className = "cm-vis-title-signatures";
      const agreed = document.createElement("div");
      appendText(agreed, "cm-vis-title-signature-heading", "СОГЛАСОВАНО");
      appendText(agreed, "", preview.supervisorRole);
      appendText(agreed, "cm-vis-title-signature-line", "");
      appendText(agreed, "", preview.supervisorName);
      if (preview.coSupervisorName) {
        appendText(
          agreed,
          "cm-vis-title-secondary",
          preview.coSupervisorRole ?? "",
        );
        appendText(agreed, "cm-vis-title-signature-line", "");
        appendText(agreed, "", preview.coSupervisorName);
      }
      const approved = document.createElement("div");
      appendText(approved, "cm-vis-title-signature-heading", "УТВЕРЖДАЮ");
      appendText(approved, "", preview.academicSupervisorRole);
      appendText(approved, "cm-vis-title-signature-line", "");
      appendText(approved, "", preview.academicSupervisorName);
      approvals.append(agreed, approved);
      approval.append(approvals);
      const approvalWork = document.createElement("div");
      approvalWork.className = "cm-vis-title-work";
      appendText(approvalWork, "cm-vis-title-project", preview.projectName);
      appendText(approvalWork, "", preview.documentName);
      appendText(approvalWork, "cm-vis-title-main-label", "ЛИСТ УТВЕРЖДЕНИЯ");
      appendText(approvalWork, "cm-vis-title-code", preview.approvalCode);
      approval.append(approvalWork);
      appendText(
        approval,
        "cm-vis-title-executor",
        `Исполнитель: ${preview.executors}\nгруппа ${preview.executorGroup}`,
      );

      const title = document.createElement("article");
      title.className = "cm-vis-title-page cm-vis-title-main";
      title.setAttribute("aria-label", i18n.t("codeEditor:visual.titleSheet"));
      appendText(
        title,
        "cm-vis-title-page-badge",
        i18n.t("codeEditor:visual.titleSheet"),
      );
      appendText(
        title,
        "cm-vis-title-approved",
        `УТВЕРЖДЕН\n${preview.approvalCode}`,
      );
      const titleWork = document.createElement("div");
      titleWork.className = "cm-vis-title-work";
      appendText(titleWork, "cm-vis-title-project", preview.projectName);
      appendText(titleWork, "cm-vis-title-document", preview.documentName);
      appendText(titleWork, "cm-vis-title-code", preview.documentCode);
      appendText(
        titleWork,
        "cm-vis-title-page-count",
        i18n.t("codeEditor:visual.pageCountAfterBuild"),
      );
      title.append(titleWork);
      appendText(title, "cm-vis-title-year", preview.year);
      pages.append(approval, title);
    } else {
      const title = document.createElement("article");
      title.className = "cm-vis-title-page cm-vis-vkr-title-page";
      title.setAttribute(
        "aria-label",
        i18n.t("codeEditor:visual.titleVkrLabel"),
      );
      appendText(
        title,
        "cm-vis-title-institution",
        `ПРАВИТЕЛЬСТВО РОССИЙСКОЙ ФЕДЕРАЦИИ\nНИУ «ВЫСШАЯ ШКОЛА ЭКОНОМИКИ»\n${preview.faculty}\nОбразовательная программа «${preview.specialization}»`,
      );
      const top = document.createElement("div");
      top.className = "cm-vis-vkr-meta";
      appendText(top, "", `УДК ${preview.udc}`);
      appendText(
        top,
        "cm-vis-vkr-approval",
        `УТВЕРЖДАЮ\n${preview.academicSupervisorRole}\n────────\n${preview.academicSupervisorName}`,
      );
      title.append(top);
      const work = document.createElement("div");
      work.className = "cm-vis-title-work";
      appendText(
        work,
        "cm-vis-title-document",
        "Выпускная квалификационная работа",
      );
      appendText(work, "cm-vis-title-topic-label", "на тему");
      appendText(work, "cm-vis-title-project", preview.projectName);
      appendText(
        work,
        "",
        `по направлению подготовки ${preview.programCode} «${preview.specialization}»`,
      );
      title.append(work);
      const people = document.createElement("div");
      people.className = "cm-vis-title-signatures cm-vis-vkr-people";
      const supervisor = document.createElement("div");
      appendText(
        supervisor,
        "cm-vis-title-signature-heading",
        "Научный руководитель",
      );
      appendText(supervisor, "", preview.supervisorRole);
      appendText(supervisor, "", preview.supervisorDegree);
      appendText(supervisor, "cm-vis-title-signature-line", "");
      appendText(supervisor, "", preview.supervisorName);
      const author = document.createElement("div");
      appendText(author, "cm-vis-title-signature-heading", "Выполнил");
      appendText(
        author,
        "",
        `студент группы ${preview.group}\n${preview.course} курса ${preview.degreeLevel}\n«${preview.specialization}»`,
      );
      appendText(author, "cm-vis-title-signature-line", "");
      appendText(author, "", preview.authorName);
      people.append(supervisor, author);
      title.append(people);
      if (preview.coSupervisorName) {
        appendText(
          title,
          "cm-vis-vkr-cosupervisor",
          `Соруководитель\n${preview.coSupervisorRole ?? ""}\n${preview.coSupervisorDegree ?? ""}\n────────\n${preview.coSupervisorName}`,
        );
      }
      appendText(title, "cm-vis-title-year", `${preview.city} ${preview.year}`);
      pages.append(title);
    }
    root.append(pages);
    return root;
  }

  override ignoreEvent(): boolean {
    return true;
  }
}

/** The reusable TZ/PMI requirements longtable rendered from its real source. */
export class RequirementsTableInputBlockWidget extends WidgetType {
  constructor(
    readonly path: string,
    readonly source: string | undefined,
    readonly onOpenFile?: (path: string) => void,
  ) {
    super();
  }

  override eq(other: RequirementsTableInputBlockWidget): boolean {
    return (
      other.path === this.path &&
      other.source === this.source &&
      Boolean(other.onOpenFile) === Boolean(this.onOpenFile)
    );
  }

  override get estimatedHeight(): number {
    const count = parseRequirementsTablePreview(this.source).rows.length;
    return 210 + Math.max(1, count) * 56;
  }

  toDOM(): HTMLElement {
    const preview = parseRequirementsTablePreview(this.source);
    const root = document.createElement("section");
    root.className = "cm-vis-source-block cm-vis-requirements";
    root.setAttribute("role", "group");
    root.setAttribute("aria-label", preview.caption);
    root.append(
      createSourceBlockToolbar({
        path: this.path,
        label: preview.caption,
        description: i18n.t("codeEditor:visual.requirementsDescription", {
          count: preview.rows.length,
        }),
        status: i18n.t("codeEditor:visual.requirementsProtected"),
        openLabel: i18n.t("codeEditor:visual.sourceOpen"),
        onOpenFile: this.onOpenFile,
      }),
    );

    const warning = document.createElement("div");
    warning.className = "cm-vis-requirements-warning";
    warning.textContent = i18n.t("codeEditor:visual.requirementsShared");

    const page = document.createElement("div");
    page.className = "cm-vis-requirements-page";
    const caption = document.createElement("div");
    caption.className = "cm-vis-requirements-caption";
    caption.textContent = `${i18n.t("codeEditor:visual.tableNumberAfterBuild")} — ${preview.caption}`;
    const scroller = document.createElement("div");
    scroller.className = "cm-vis-requirements-scroll";
    const table = document.createElement("table");
    table.className = "cm-vis-requirements-table";
    table.setAttribute("aria-label", preview.caption);
    const colgroup = document.createElement("colgroup");
    for (const width of [14, 29, 34, 23]) {
      const col = document.createElement("col");
      col.style.width = `${String(width)}%`;
      colgroup.append(col);
    }
    table.append(colgroup);
    const thead = document.createElement("thead");
    const headerRow = document.createElement("tr");
    for (const header of preview.headers) {
      const cell = document.createElement("th");
      cell.scope = "col";
      cell.textContent = header;
      headerRow.append(cell);
    }
    thead.append(headerRow);
    table.append(thead);
    const tbody = document.createElement("tbody");
    for (const row of preview.rows) {
      const tr = document.createElement("tr");
      for (const value of [row.id, row.userStory, row.requirement, row.area]) {
        const cell = document.createElement("td");
        cell.textContent = value;
        tr.append(cell);
      }
      tbody.append(tr);
    }
    if (preview.rows.length === 0) {
      const tr = document.createElement("tr");
      const cell = document.createElement("td");
      cell.colSpan = 4;
      cell.className = "cm-vis-requirements-empty";
      cell.textContent = i18n.t(
        this.source === undefined
          ? "codeEditor:visual.inputLoading"
          : "codeEditor:visual.requirementsEmpty",
      );
      tr.append(cell);
      tbody.append(tr);
    }
    table.append(tbody);
    scroller.append(table);
    page.append(caption, scroller);
    root.append(warning, page);
    return root;
  }

  override ignoreEvent(): boolean {
    return true;
  }
}

/** A literal glyph replacement (`~` → nbsp, `\ldots` → …). */
export class SymbolWidget extends WidgetType {
  constructor(
    readonly glyph: string,
    readonly className: string,
  ) {
    super();
  }

  override eq(other: SymbolWidget): boolean {
    return other.glyph === this.glyph && other.className === this.className;
  }

  toDOM(view: EditorView): HTMLElement {
    const span = document.createElement("span");
    span.className = this.className;
    span.textContent = this.glyph;
    revealOnMouseDown(span, view);
    return span;
  }

  override ignoreEvent(): boolean {
    return true;
  }
}

/**
 * The shared ГОСТ registration sheet. It is source-backed (row count and
 * values come from change_log.tex) but intentionally read-only here: the main
 * document owns only its input reference, and the included file is shared.
 */
export class ChangeLogInputBlockWidget extends WidgetType {
  constructor(
    readonly path: string,
    readonly source: string | undefined,
    readonly docCode: string | undefined,
    readonly onOpenFile?: (path: string) => void,
  ) {
    super();
  }

  override eq(other: ChangeLogInputBlockWidget): boolean {
    return (
      other.path === this.path &&
      other.source === this.source &&
      other.docCode === this.docCode &&
      Boolean(other.onOpenFile) === Boolean(this.onOpenFile)
    );
  }

  override get estimatedHeight(): number {
    return 650;
  }

  toDOM(): HTMLElement {
    const preview = parseChangeLogPreview(this.source);
    const root = document.createElement("section");
    root.className = "cm-vis-change-log";
    root.setAttribute("role", "group");
    root.setAttribute("aria-label", i18n.t("codeEditor:visual.changeLogLabel"));

    const toolbar = document.createElement("header");
    toolbar.className = "cm-vis-change-log-toolbar";
    const copy = document.createElement("span");
    copy.className = "cm-vis-change-log-copy";
    const label = document.createElement("strong");
    label.textContent = preview.tableTitle;
    const description = document.createElement("span");
    description.textContent = i18n.t("codeEditor:visual.changeLogDescription", {
      count: preview.rows.length,
    });
    const source = document.createElement("code");
    source.textContent = this.path.split("/").pop() ?? this.path;
    copy.append(label, description, source);

    const status = document.createElement("span");
    status.className = "cm-vis-change-log-status";
    status.textContent = i18n.t("codeEditor:visual.changeLogProtected");
    toolbar.append(copy, status);

    if (this.onOpenFile) {
      const open = document.createElement("button");
      open.type = "button";
      open.className = "cm-vis-change-log-open";
      open.textContent = i18n.t("codeEditor:visual.changeLogOpen");
      open.addEventListener("mousedown", (event) => {
        event.preventDefault();
        event.stopPropagation();
      });
      open.addEventListener("click", (event) => {
        event.preventDefault();
        event.stopPropagation();
        this.onOpenFile?.(this.path);
      });
      toolbar.append(open);
    }

    const warning = document.createElement("div");
    warning.className = "cm-vis-change-log-warning";
    warning.textContent = i18n.t("codeEditor:visual.changeLogShared");

    const page = document.createElement("div");
    page.className = "cm-vis-change-log-page";
    const pageHeader = document.createElement("div");
    pageHeader.className = "cm-vis-change-log-page-header";
    const pageNumber = document.createElement("span");
    pageNumber.textContent = "—";
    pageNumber.title = i18n.t("codeEditor:visual.changeLogPagePending");
    const documentCode = document.createElement("span");
    documentCode.textContent = (this.docCode ?? "")
      .replace(/\\ /g, " ")
      .replace(/~/g, " ")
      .trim();
    pageHeader.append(pageNumber, documentCode);

    const pageTitle = document.createElement("div");
    pageTitle.className = "cm-vis-change-log-page-title";
    pageTitle.textContent = preview.title;

    const scroller = document.createElement("div");
    scroller.className = "cm-vis-change-log-table-scroll";
    const table = document.createElement("table");
    table.className = "cm-vis-change-log-table";
    table.setAttribute("aria-label", preview.tableTitle);

    const colgroup = document.createElement("colgroup");
    for (const width of [7, 7, 7, 7, 7, 10, 11, 22, 10, 12]) {
      const col = document.createElement("col");
      col.style.width = String(width) + "%";
      colgroup.append(col);
    }
    table.append(colgroup);

    const thead = document.createElement("thead");
    const titleRow = document.createElement("tr");
    const tableTitle = document.createElement("th");
    tableTitle.colSpan = 10;
    tableTitle.textContent = preview.tableTitle;
    titleRow.append(tableTitle);

    const grouped = document.createElement("tr");
    const pageNumbers = document.createElement("th");
    pageNumbers.colSpan = 5;
    pageNumbers.textContent = "Номера листов (страниц)";
    grouped.append(pageNumbers);
    for (const text of [
      "Всего листов (страниц) в докум.",
      "№ документа",
      "Входящий № сопров. докум. и дата",
      "Подп.",
      "Дата",
    ]) {
      const cell = document.createElement("th");
      cell.rowSpan = 2;
      cell.textContent = text;
      grouped.append(cell);
    }

    const detail = document.createElement("tr");
    for (const text of [
      "Изм.",
      "Изменённых",
      "Заменённых",
      "Новых",
      "Аннулированных",
    ]) {
      const cell = document.createElement("th");
      cell.textContent = text;
      detail.append(cell);
    }
    thead.append(titleRow, grouped, detail);
    table.append(thead);

    const tbody = document.createElement("tbody");
    for (const row of preview.rows) {
      const tr = document.createElement("tr");
      for (const value of row) {
        const cell = document.createElement("td");
        cell.textContent = value;
        tr.append(cell);
      }
      tbody.append(tr);
    }
    table.append(tbody);
    scroller.append(table);
    page.append(pageHeader, pageTitle, scroller);
    root.append(toolbar, warning, page);
    return root;
  }

  override ignoreEvent(): boolean {
    return true;
  }
}

/** A run of full-line comments collapsed into one unobtrusive line. */
export class CommentBlockWidget extends WidgetType {
  constructor(readonly lineCount: number) {
    super();
  }

  override eq(other: CommentBlockWidget): boolean {
    return other.lineCount === this.lineCount;
  }

  toDOM(view: EditorView): HTMLElement {
    const el = document.createElement("div");
    el.className = "cm-vis-commentblock";
    el.textContent = `⌇ ${i18n.t("codeEditor:visual.commentLines", {
      count: this.lineCount,
    })}`;
    el.title = i18n.t("codeEditor:visual.commentExpand");
    revealOnMouseDown(el, view, true);
    return el;
  }

  override ignoreEvent(): boolean {
    return true;
  }
}

/** `\\` line break rendered as a subtle return glyph. */
export class LineBreakWidget extends WidgetType {
  override eq(): boolean {
    return true;
  }

  toDOM(view: EditorView): HTMLElement {
    const span = document.createElement("span");
    span.className = "cm-vis-linebreak";
    span.textContent = "↵";
    revealOnMouseDown(span, view);
    return span;
  }

  override ignoreEvent(): boolean {
    return true;
  }
}

/** Header row shared by the inline block cards (table / figure / environment). */
const createCardHeader = (
  icon: string,
  label: string,
  hint: string,
): HTMLElement => {
  const header = document.createElement("header");
  header.className = "cm-vis-card-head";
  const iconEl = document.createElement("span");
  iconEl.className = "cm-vis-card-icon";
  iconEl.textContent = icon;
  const labelEl = document.createElement("span");
  labelEl.className = "cm-vis-card-label";
  labelEl.textContent = label;
  const hintEl = document.createElement("span");
  hintEl.className = "cm-vis-card-hint";
  hintEl.textContent = hint;
  header.append(iconEl, labelEl, hintEl);
  return header;
};

/** Fill a table row with exactly `columnCount` cells, padding short rows. */
const appendTableCells = (
  row: HTMLElement,
  tag: "th" | "td",
  values: readonly string[],
  columnCount: number,
): void => {
  for (let index = 0; index < columnCount; index += 1) {
    const cell = document.createElement(tag);
    cell.textContent = values[index] ?? "";
    row.append(cell);
  }
};

type EditTableCallback = (
  source: string,
  commit: (next: string) => void,
) => void;

/** Move the caret to the widget so its raw LaTeX is revealed for editing. */
const revealWidgetSource = (view: EditorView, dom: HTMLElement): void => {
  const pos = view.posAtDOM(dom);
  view.dispatch({ selection: { anchor: pos }, scrollIntoView: true });
  view.focus();
};

/** A header button that reveals the raw source of a card. */
const createShowSourceButton = (
  view: EditorView,
  root: HTMLElement,
): HTMLElement => {
  const button = document.createElement("button");
  button.type = "button";
  button.className = "cm-vis-card-code";
  button.textContent = "</>";
  button.title = i18n.t("codeEditor:visual.showSource");
  button.setAttribute("aria-label", i18n.t("codeEditor:visual.showSource"));
  button.addEventListener("mousedown", (event) => {
    event.preventDefault();
    event.stopPropagation();
    revealWidgetSource(view, root);
  });
  addKeyboardActivation(button, () => revealWidgetSource(view, root));
  return button;
};

export type EditBibliographyCallback = (
  source: string,
  commit: (next: string) => void,
) => void;

/**
 * Open the structured bibliography manager for the enclosing `thebibliography`.
 * The env range is resolved at click time from the widget's own DOM position
 * (which never goes stale) minus its build-time offset into the env; a mismatch
 * falls back to revealing the raw source, like a table card.
 */
const openBibliographyEditor = (
  view: EditorView,
  root: HTMLElement,
  source: string,
  anchorOffset: number,
  onEdit: EditBibliographyCallback,
): void => {
  const from = view.posAtDOM(root) - anchorOffset;
  const to = from + source.length;
  if (from < 0 || view.state.doc.sliceString(from, to) !== source) {
    revealWidgetSource(view, root);
    return;
  }
  onEdit(source, (next) => {
    if (view.state.doc.sliceString(from, to) !== source) return;
    view.dispatch({ changes: { from, to, insert: next }, userEvent: "input" });
    view.focus();
  });
};

/** A «Управлять»/«Добавить» button that opens the bibliography manager. */
const createBibManageButton = (
  view: EditorView,
  root: HTMLElement,
  source: string,
  anchorOffset: number,
  onEdit: EditBibliographyCallback,
  label: string,
  className: string,
): HTMLElement => {
  const button = document.createElement("button");
  button.type = "button";
  button.className = className;
  button.textContent = label;
  button.title = label;
  button.setAttribute("aria-label", label);
  const open = (): void => {
    openBibliographyEditor(view, root, source, anchorOffset, onEdit);
  };
  button.addEventListener("mousedown", (event) => {
    event.preventDefault();
    event.stopPropagation();
    open();
  });
  addKeyboardActivation(button, open);
  return button;
};

/**
 * The `\begin{thebibliography}{…}` line, shown as a titled header instead of
 * raw markup. When the host wires `onEditBibliography` it carries a «Управлять»
 * button that opens the structured manager for the whole environment.
 */
export class BibHeaderWidget extends WidgetType {
  constructor(
    readonly source: string,
    readonly onEdit?: EditBibliographyCallback,
  ) {
    super();
  }

  override eq(other: BibHeaderWidget): boolean {
    return (
      other.source === this.source &&
      Boolean(other.onEdit) === Boolean(this.onEdit)
    );
  }

  toDOM(view: EditorView): HTMLElement {
    const root = document.createElement("span");
    root.className = "cm-vis-bib-head";
    const icon = document.createElement("span");
    icon.className = "cm-vis-bib-head-icon";
    icon.textContent = "📚";
    const label = document.createElement("span");
    label.className = "cm-vis-bib-head-label";
    label.textContent = i18n.t("codeEditor:visual.bibliographyTitle");
    root.append(icon, label);
    if (this.onEdit) {
      root.append(
        createBibManageButton(
          view,
          root,
          this.source,
          0,
          this.onEdit,
          i18n.t("codeEditor:visual.bibliographyManage"),
          "cm-vis-bib-manage",
        ),
      );
    }
    return root;
  }

  override ignoreEvent(): boolean {
    return true;
  }
}

/**
 * The `\end{thebibliography}` marker, shown as a «+ Добавить источник» footer
 * that opens the manager (offset back to the env start resolved at click time).
 */
export class BibFooterWidget extends WidgetType {
  constructor(
    readonly source: string,
    readonly anchorOffset: number,
    readonly onEdit?: EditBibliographyCallback,
  ) {
    super();
  }

  override eq(other: BibFooterWidget): boolean {
    return (
      other.source === this.source &&
      other.anchorOffset === this.anchorOffset &&
      Boolean(other.onEdit) === Boolean(this.onEdit)
    );
  }

  toDOM(view: EditorView): HTMLElement {
    const root = document.createElement("span");
    root.className = "cm-vis-bib-foot";
    if (this.onEdit) {
      root.append(
        createBibManageButton(
          view,
          root,
          this.source,
          this.anchorOffset,
          this.onEdit,
          i18n.t("codeEditor:visual.bibliographyAdd"),
          "cm-vis-bib-add",
        ),
      );
    }
    return root;
  }

  override ignoreEvent(): boolean {
    return true;
  }
}

/**
 * A `\bibitem{key}` marker, shown as a numbered badge plus a subtle citation-key
 * chip (the key is what `\cite{…}` references). The reference text after it
 * stays as ordinary editable prose. Click reveals the raw marker to edit the key.
 */
export class BibItemBadgeWidget extends WidgetType {
  constructor(
    readonly ordinal: number,
    readonly key: string,
  ) {
    super();
  }

  override eq(other: BibItemBadgeWidget): boolean {
    return other.ordinal === this.ordinal && other.key === this.key;
  }

  toDOM(view: EditorView): HTMLElement {
    const root = document.createElement("span");
    root.className = "cm-vis-bibitem";
    const num = document.createElement("span");
    num.className = "cm-vis-bibitem-num";
    num.textContent = `${String(this.ordinal)}.`;
    root.append(num);
    if (this.key) {
      const chip = document.createElement("span");
      chip.className = "cm-vis-bibitem-key";
      chip.textContent = this.key;
      chip.title = i18n.t("codeEditor:visual.bibliographyKeyHint");
      root.append(chip);
    }
    revealOnMouseDown(root, view);
    return root;
  }
}

/**
 * Wire a table card so clicking it opens the structured editor. Position and
 * length are resolved at click time (never build time — they go stale while
 * `eq()` keeps the DOM alive); a mismatch falls back to revealing the source.
 */
const attachTableEditor = (
  root: HTMLElement,
  view: EditorView,
  source: string,
  onEditTable: EditTableCallback,
): void => {
  const open = (): void => {
    const from = view.posAtDOM(root);
    const to = from + source.length;
    if (view.state.doc.sliceString(from, to) !== source) {
      revealWidgetSource(view, root);
      return;
    }
    onEditTable(source, (next) => {
      if (view.state.doc.sliceString(from, to) !== source) return;
      view.dispatch({
        changes: { from, to, insert: next },
        userEvent: "input",
      });
      view.focus();
    });
  };
  root.addEventListener("mousedown", (event) => {
    if (event.button !== 0 || event.ctrlKey || event.metaKey) return;
    event.preventDefault();
    open();
  });
  addKeyboardActivation(root, open, i18n.t("codeEditor:visual.tableEditHint"));
};

/**
 * A `table` / `tabular` / `longtable` environment rendered as a real table,
 * Word-style. When the host wires `onEditTable` (and the table round-trips
 * safely) the card opens a structured cell editor; otherwise clicking reveals
 * the raw LaTeX, like formulas. The parse is a printable projection, never run.
 */
export class TableBlockWidget extends WidgetType {
  constructor(
    readonly source: string,
    readonly onEditTable?: EditTableCallback,
  ) {
    super();
  }

  override eq(other: TableBlockWidget): boolean {
    return (
      other.source === this.source &&
      Boolean(other.onEditTable) === Boolean(this.onEditTable)
    );
  }

  override get estimatedHeight(): number {
    const preview = parseTablePreview(this.source);
    const rows = preview.rows.length + (preview.headers.length ? 1 : 0);
    return 92 + Math.max(1, rows) * 30;
  }

  toDOM(view: EditorView): HTMLElement {
    const preview = parseTablePreview(this.source);
    const label = preview.caption ?? i18n.t("codeEditor:visual.tableCard");
    const columnCount = Math.max(
      preview.headers.length,
      ...preview.rows.map((row) => row.length),
      1,
    );
    const canEdit =
      Boolean(this.onEditTable) &&
      (parseEditableTable(this.source)?.scaffold.editable ?? false);
    const root = document.createElement("section");
    root.className = "cm-vis-card cm-vis-doc-table";
    root.setAttribute("role", "group");
    root.setAttribute("aria-label", label);
    const header = createCardHeader(
      "▦",
      label,
      i18n.t(
        canEdit
          ? "codeEditor:visual.tableEditHint"
          : "codeEditor:visual.cardEditHint",
      ),
    );
    if (canEdit) header.append(createShowSourceButton(view, root));
    root.append(header);

    if (preview.headers.length === 0 && preview.rows.length === 0) {
      const note = document.createElement("div");
      note.className = "cm-vis-card-empty";
      note.textContent = i18n.t("codeEditor:visual.tableCardEmpty");
      root.append(note);
    } else {
      const scroller = document.createElement("div");
      scroller.className = "cm-vis-doc-table-scroll";
      const table = document.createElement("table");
      table.className = "cm-vis-doc-table-grid";
      if (preview.headers.length) {
        const thead = document.createElement("thead");
        const headerRow = document.createElement("tr");
        appendTableCells(headerRow, "th", preview.headers, columnCount);
        thead.append(headerRow);
        table.append(thead);
      }
      const tbody = document.createElement("tbody");
      for (const row of preview.rows) {
        const tr = document.createElement("tr");
        appendTableCells(tr, "td", row, columnCount);
        tbody.append(tr);
      }
      table.append(tbody);
      scroller.append(table);
      root.append(scroller);
    }
    if (canEdit && this.onEditTable) {
      attachTableEditor(root, view, this.source, this.onEditTable);
    } else {
      revealOnMouseDown(root, view, true);
    }
    return root;
  }

  override ignoreEvent(): boolean {
    return true;
  }
}

/**
 * A `figure` environment rendered as an image card: the real picture (when the
 * host resolves a URL) plus its caption. Click reveals the raw LaTeX to edit.
 */
export class FigureBlockWidget extends WidgetType {
  constructor(
    readonly source: string,
    readonly resolveAssetUrl?: (path: string) => string | null,
  ) {
    super();
  }

  override eq(other: FigureBlockWidget): boolean {
    return (
      other.source === this.source &&
      Boolean(other.resolveAssetUrl) === Boolean(this.resolveAssetUrl)
    );
  }

  override get estimatedHeight(): number {
    return 250;
  }

  toDOM(view: EditorView): HTMLElement {
    const preview = parseFigurePreview(this.source);
    const label = preview.caption ?? i18n.t("codeEditor:visual.figureCard");
    const root = document.createElement("section");
    root.className = "cm-vis-card cm-vis-figure";
    root.setAttribute("role", "group");
    root.setAttribute("aria-label", label);
    root.append(
      createCardHeader("🖼", label, i18n.t("codeEditor:visual.cardEditHint")),
    );

    const body = document.createElement("div");
    body.className = "cm-vis-figure-body";
    const url = preview.image
      ? (this.resolveAssetUrl?.(preview.image) ?? null)
      : null;
    if (url && preview.image) {
      const img = document.createElement("img");
      img.src = url;
      img.alt = preview.image;
      img.loading = "lazy";
      img.draggable = false;
      const name = document.createElement("span");
      name.className = "cm-vis-figure-name";
      name.textContent = preview.image.split("/").pop() ?? preview.image;
      img.addEventListener("error", () => {
        body.classList.add("cm-vis-figure-broken");
        name.textContent = `⚠ ${preview.image ?? ""}`;
      });
      body.append(img, name);
    } else {
      const placeholder = document.createElement("div");
      placeholder.className = "cm-vis-figure-empty";
      placeholder.textContent =
        preview.image ?? i18n.t("codeEditor:visual.figureNoImage");
      body.append(placeholder);
    }
    root.append(body);
    revealOnMouseDown(root, view, true);
    return root;
  }

  override ignoreEvent(): boolean {
    return true;
  }
}

const MAX_ENV_PEEK_CHARS = 220;

/** A friendly label for a code/drawing environment, falling back to its name. */
const environmentLabel = (name: string): string =>
  i18n.t(`codeEditor:visual.env.${name}`, {
    defaultValue: i18n.t("codeEditor:visual.environmentCard", { name }),
  });

/** The environment body between its `\begin`/`\end` lines, as a short peek. */
const environmentPeek = (source: string): string => {
  const lines = source.split("\n");
  return lines
    .slice(1, Math.max(1, lines.length - 1))
    .join(" ")
    .replace(/\s+/g, " ")
    .trim()
    .slice(0, MAX_ENV_PEEK_CHARS);
};

/**
 * A non-prose environment (tikzpicture, verbatim, lstlisting…) rendered as a
 * named card with a short inert peek instead of raw source. Click reveals the
 * real LaTeX to edit.
 */
export class EnvironmentBlockWidget extends WidgetType {
  constructor(
    readonly name: string,
    readonly source: string,
  ) {
    super();
  }

  override eq(other: EnvironmentBlockWidget): boolean {
    return other.name === this.name && other.source === this.source;
  }

  override get estimatedHeight(): number {
    return 108;
  }

  toDOM(view: EditorView): HTMLElement {
    const root = document.createElement("section");
    root.className = "cm-vis-card cm-vis-envcard";
    root.setAttribute("role", "group");
    root.setAttribute("aria-label", environmentLabel(this.name));
    root.append(
      createCardHeader(
        "❯_",
        environmentLabel(this.name),
        i18n.t("codeEditor:visual.cardEditHint"),
      ),
    );
    const peek = environmentPeek(this.source);
    if (peek) {
      const body = document.createElement("div");
      body.className = "cm-vis-envcard-peek";
      body.textContent = peek;
      root.append(body);
    }
    revealOnMouseDown(root, view, true);
    return root;
  }

  override ignoreEvent(): boolean {
    return true;
  }
}
