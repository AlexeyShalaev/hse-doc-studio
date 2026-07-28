import { useLayoutEffect, useRef } from "react";
import { htmlToLatex, latexToHtml } from "@shared/ui";
import { applyInlineFormat } from "../lib/inlineFormat";

export type RichCellProps = {
  /** The cell's inline LaTeX (may contain \textbf/\textit/…). */
  value: string;
  ariaLabel: string;
  onChange: (value: string) => void;
};

/**
 * A single table cell edited as rich text. The contenteditable's HTML is owned
 * *entirely imperatively* — the JSX renders an empty div with no children and
 * no `dangerouslySetInnerHTML`, so React never re-commits (and thus never wipes)
 * the content on the re-render that follows each keystroke. We paint it on mount
 * and again only when `value` changes from the outside (undo/redo, reset); our
 * own edits flow out through `onChange` as inline LaTeX and are left alone.
 */
export const RichCell = ({ value, ariaLabel, onChange }: RichCellProps) => {
  const ref = useRef<HTMLDivElement>(null);
  // The last LaTeX we painted into / read out of the DOM. `null` until the first
  // paint, so the mount pass always runs; then it distinguishes an external
  // change (re-paint) from our own edit (leave the DOM, and the caret, alone).
  const lastValue = useRef<string | null>(null);

  // Layout effect (before paint → no flash of empty cell). Mount paints; later
  // it re-paints only when an outside change makes `value` diverge from the DOM.
  useLayoutEffect(() => {
    const element = ref.current;
    if (!element) return;
    if (value !== lastValue.current) {
      element.innerHTML = latexToHtml(value);
      lastValue.current = value;
    }
  }, [value]);

  const emit = (): void => {
    const element = ref.current;
    if (!element) return;
    const next = htmlToLatex(element);
    lastValue.current = next;
    onChange(next);
  };

  const handleKeyDown = (event: React.KeyboardEvent<HTMLDivElement>): void => {
    if (event.ctrlKey || event.metaKey) {
      // Key off the physical code so the shortcut works under a Cyrillic layout
      // (event.key would be «и»/«ш»/«г»); fall back to the character too.
      const code = event.code;
      const key = event.key.toLowerCase();
      const command =
        code === "KeyB" || key === "b"
          ? "bold"
          : code === "KeyI" || key === "i"
            ? "italic"
            : code === "KeyU" || key === "u"
              ? "underline"
              : null;
      if (command) {
        event.preventDefault();
        applyInlineFormat(command);
      }
      return; // let Ctrl+Z/Y bubble to the modal's history handler
    }
    if (event.key === "Enter") event.preventDefault(); // cells stay single-block
  };

  const handlePaste = (event: React.ClipboardEvent<HTMLDivElement>): void => {
    // Paste as plain text — arbitrary pasted HTML would smuggle in tags the
    // serializer can't map back to LaTeX.
    event.preventDefault();
    const text = event.clipboardData.getData("text/plain");
    document.execCommand("insertText", false, text);
  };

  return (
    <div
      ref={ref}
      contentEditable
      suppressContentEditableWarning
      role="textbox"
      aria-multiline="true"
      aria-label={ariaLabel}
      className="cm-vis-rich-cell"
      onInput={emit}
      onKeyDown={handleKeyDown}
      onPaste={handlePaste}
    />
  );
};

RichCell.displayName = "RichCell";
