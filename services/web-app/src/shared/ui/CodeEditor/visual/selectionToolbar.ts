import { type EditorSelection } from "@codemirror/state";
import { ViewPlugin, type EditorView, type ViewUpdate } from "@codemirror/view";
import { i18n } from "@shared/lib";
import { runEditorCommand } from "../formatCommands";
import type { EditorCommandId } from "../types";

type Box = {
  top: number;
  right: number;
  bottom: number;
  left: number;
};

export type SelectionToolbarPositionInput = {
  editor: Box;
  selection: Box;
  toolbarWidth: number;
  toolbarHeight: number;
  viewportWidth: number;
  viewportHeight: number;
  gap?: number;
  margin?: number;
};

export type SelectionToolbarPosition = {
  left: number;
  top: number;
  placement: "above" | "below";
};

const clamp = (value: number, min: number, max: number): number =>
  Math.min(Math.max(value, min), max);

/**
 * Keep the floating bar inside both the editor and the browser viewport.
 * Prefer the conventional position above the selection, then fall back below
 * it when the selection is too close to the top edge.
 */
export const computeSelectionToolbarPosition = ({
  editor,
  selection,
  toolbarWidth,
  toolbarHeight,
  viewportWidth,
  viewportHeight,
  gap = 8,
  margin = 8,
}: SelectionToolbarPositionInput): SelectionToolbarPosition | null => {
  const visibleLeft = Math.max(editor.left, 0) + margin;
  const visibleRight = Math.min(editor.right, viewportWidth) - margin;
  const visibleTop = Math.max(editor.top, 0) + margin;
  const visibleBottom = Math.min(editor.bottom, viewportHeight) - margin;

  if (
    visibleRight <= visibleLeft ||
    visibleBottom <= visibleTop ||
    selection.bottom < visibleTop ||
    selection.top > visibleBottom
  ) {
    return null;
  }

  const maxLeft = Math.max(visibleLeft, visibleRight - toolbarWidth);
  const selectionCenter = (selection.left + selection.right) / 2;
  const left = clamp(selectionCenter - toolbarWidth / 2, visibleLeft, maxLeft);

  const above = selection.top - gap - toolbarHeight;
  const below = selection.bottom + gap;
  if (above >= visibleTop) {
    return { left, top: above, placement: "above" };
  }
  if (below + toolbarHeight <= visibleBottom) {
    return { left, top: below, placement: "below" };
  }

  // A very small editor can have room on neither side. Keep the toolbar
  // reachable and stable instead of letting it escape under surrounding UI.
  const top = clamp(
    above,
    visibleTop,
    Math.max(visibleTop, visibleBottom - toolbarHeight),
  );
  return {
    left,
    top,
    placement: top < selection.top ? "above" : "below",
  };
};

type ToolbarAction = {
  id: Extract<EditorCommandId, "bold" | "italic" | "underline" | "monospace">;
  labelKey: "bold" | "italic" | "underline" | "monospace";
  text: string;
  style?: Partial<CSSStyleDeclaration>;
};

const ACTIONS: readonly ToolbarAction[] = [
  { id: "bold", labelKey: "bold", text: "B", style: { fontWeight: "700" } },
  {
    id: "italic",
    labelKey: "italic",
    text: "I",
    style: { fontStyle: "italic" },
  },
  {
    id: "underline",
    labelKey: "underline",
    text: "U",
    style: { textDecoration: "underline" },
  },
  {
    id: "monospace",
    labelKey: "monospace",
    text: "</>",
    style: { fontFamily: "var(--font-mono)", fontSize: "10px" },
  },
];

class SelectionToolbarPlugin {
  private readonly toolbar: HTMLDivElement;
  private readonly ownerWindow: Window;
  private frame = 0;
  private savedSelection: EditorSelection | null = null;

  private readonly schedulePosition = (): void => {
    if (this.frame !== 0) return;
    this.frame = this.ownerWindow.requestAnimationFrame(() => {
      this.frame = 0;
      this.position();
    });
  };

  constructor(private readonly view: EditorView) {
    const ownerDocument = view.dom.ownerDocument;
    this.ownerWindow = ownerDocument.defaultView ?? window;
    this.toolbar = ownerDocument.createElement("div");
    this.toolbar.className = "cm-vis-selection-toolbar";
    this.toolbar.setAttribute("role", "toolbar");
    this.toolbar.setAttribute("aria-hidden", "true");
    Object.assign(this.toolbar.style, {
      position: "fixed",
      zIndex: "1000",
      display: "none",
      alignItems: "center",
      gap: "2px",
      padding: "4px",
      boxSizing: "border-box",
      border: "1px solid var(--border)",
      borderRadius: "7px",
      background: "var(--bg-1)",
      boxShadow: "0 8px 24px color-mix(in srgb, #000 20%, transparent)",
    } satisfies Partial<CSSStyleDeclaration>);

    for (const action of ACTIONS) {
      this.toolbar.appendChild(this.buildButton(action));
    }
    ownerDocument.body.appendChild(this.toolbar);

    // The editor scroller is not the only possible moving ancestor. Capture
    // scroll events on window as well so nested workspace panes stay aligned.
    view.scrollDOM.addEventListener("scroll", this.schedulePosition, {
      passive: true,
    });
    this.ownerWindow.addEventListener("scroll", this.schedulePosition, true);
    this.ownerWindow.addEventListener("resize", this.schedulePosition);
    this.schedulePosition();
  }

  update(update: ViewUpdate): void {
    if (
      update.selectionSet ||
      update.docChanged ||
      update.focusChanged ||
      update.geometryChanged ||
      update.viewportChanged ||
      update.startState.readOnly !== update.state.readOnly
    ) {
      this.schedulePosition();
    }
  }

  destroy(): void {
    if (this.frame !== 0) {
      this.ownerWindow.cancelAnimationFrame(this.frame);
      this.frame = 0;
    }
    this.view.scrollDOM.removeEventListener("scroll", this.schedulePosition);
    this.ownerWindow.removeEventListener("scroll", this.schedulePosition, true);
    this.ownerWindow.removeEventListener("resize", this.schedulePosition);
    this.toolbar.remove();
  }

  private buildButton(action: ToolbarAction): HTMLButtonElement {
    const button = this.view.dom.ownerDocument.createElement("button");
    const label = i18n.t(`sourceEdit:format.${action.labelKey}`);
    button.type = "button";
    button.className =
      "cm-vis-selection-toolbar-button cm-vis-selection-toolbar-" + action.id;
    button.textContent = action.text;
    button.title = label;
    button.setAttribute("aria-label", label);
    Object.assign(
      button.style,
      {
        display: "inline-flex",
        alignItems: "center",
        justifyContent: "center",
        width: "28px",
        height: "26px",
        padding: "0",
        border: "none",
        borderRadius: "4px",
        background: "transparent",
        color: "var(--fg-0)",
        cursor: "pointer",
        lineHeight: "1",
      } satisfies Partial<CSSStyleDeclaration>,
      action.style,
    );

    button.addEventListener("mousedown", (event) => {
      if (event.button !== 0) return;
      // Prevent the browser from moving focus to the button and collapsing
      // CodeMirror's selection before the click command can consume it.
      event.preventDefault();
      this.savedSelection = this.view.state.selection;
    });
    button.addEventListener("click", (event) => {
      event.preventDefault();
      const saved = this.savedSelection;
      this.savedSelection = null;
      if (
        saved?.ranges.every(
          (range) => range.to <= this.view.state.doc.length,
        ) === true
      ) {
        this.view.dispatch({ selection: saved });
      }
      runEditorCommand(this.view, action.id);
      this.view.focus();
      this.schedulePosition();
    });
    return button;
  }

  private hide(): void {
    this.toolbar.style.display = "none";
    this.toolbar.style.visibility = "hidden";
    this.toolbar.setAttribute("aria-hidden", "true");
  }

  private position(): void {
    const selection = this.view.state.selection.main;
    if (!this.view.hasFocus || this.view.state.readOnly || selection.empty) {
      this.hide();
      return;
    }

    const start = this.view.coordsAtPos(selection.from, 1);
    const end = this.view.coordsAtPos(selection.to, -1);
    if (!start || !end) {
      this.hide();
      return;
    }

    // Make the element measurable without flashing at its previous position.
    this.toolbar.style.display = "flex";
    this.toolbar.style.visibility = "hidden";
    const toolbarRect = this.toolbar.getBoundingClientRect();
    const editorRect = this.view.scrollDOM.getBoundingClientRect();
    const position = computeSelectionToolbarPosition({
      editor: editorRect,
      selection: {
        top: Math.min(start.top, end.top),
        right: Math.max(start.right, end.right),
        bottom: Math.max(start.bottom, end.bottom),
        left: Math.min(start.left, end.left),
      },
      toolbarWidth: toolbarRect.width,
      toolbarHeight: toolbarRect.height,
      viewportWidth: this.ownerWindow.innerWidth,
      viewportHeight: this.ownerWindow.innerHeight,
    });
    if (!position) {
      this.hide();
      return;
    }

    this.toolbar.style.left = `${String(Math.round(position.left))}px`;
    this.toolbar.style.top = `${String(Math.round(position.top))}px`;
    this.toolbar.dataset.placement = position.placement;
    this.toolbar.style.visibility = "visible";
    this.toolbar.setAttribute("aria-hidden", "false");
  }
}

/** Contextual formatting controls for a non-empty visual-mode selection. */
export const selectionToolbarExtension = ViewPlugin.fromClass(
  SelectionToolbarPlugin,
);
