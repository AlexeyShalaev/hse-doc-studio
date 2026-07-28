/**
 * Apply an inline format (bold/italic/underline) to the current selection in
 * the focused rich-text cell. `execCommand` is deprecated but remains the
 * simplest, best-supported way to toggle formatting inside a contenteditable;
 * `styleWithCSS=false` makes it emit tags (`<b>`/`<i>`/`<u>`) the serializer
 * maps back to LaTeX, not inline styles.
 */
export const applyInlineFormat = (
  command: "bold" | "italic" | "underline",
): void => {
  document.execCommand("styleWithCSS", false, "false");
  document.execCommand(command);
  // execCommand doesn't always emit `input`; nudge the focused cell to re-read.
  document.activeElement?.dispatchEvent(new Event("input", { bubbles: true }));
};
