import { useState } from "react";
import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

// RichCell imports the `@shared/ui` barrel, which eagerly loads pdfjs-dist
// (needs DOMMatrix, absent in jsdom). We never render the PDF viewer here.
vi.mock("pdfjs-dist", () => ({
  GlobalWorkerOptions: {},
  getDocument: () => ({ promise: Promise.resolve(null) }),
  version: "0",
}));

import { RichCell } from "./RichCell";

/** Parent that stores the cell value exactly like TableEditorModal does. */
const Harness = ({ initial = "" }: { initial?: string }) => {
  const [value, setValue] = useState(initial);
  return (
    <div>
      <RichCell value={value} ariaLabel="c" onChange={setValue} />
      <output data-testid="stored">{value}</output>
    </div>
  );
};

/** Simulate a keystroke: mutate the contenteditable DOM, then fire `input`. */
const type = (cell: HTMLElement, text: string): void => {
  cell.textContent = text;
  fireEvent.input(cell);
};

const stored = (): string | null => screen.getByTestId("stored").textContent;

describe("RichCell", () => {
  it("keeps typed text in the DOM after the parent re-renders", () => {
    render(<Harness />);
    const cell = screen.getByRole("textbox");
    type(cell, "abc");
    // The parent stored the edit …
    expect(stored()).toBe("abc");
    // … and React did NOT wipe the contenteditable on the re-render.
    expect(cell.textContent).toBe("abc");
  });

  it("keeps typing across several keystrokes", () => {
    render(<Harness />);
    const cell = screen.getByRole("textbox");
    type(cell, "a");
    type(cell, "ab");
    type(cell, "abc");
    expect(cell.textContent).toBe("abc");
    expect(stored()).toBe("abc");
  });

  it("preserves a normal space between words (not a ~)", () => {
    render(<Harness />);
    const cell = screen.getByRole("textbox");
    type(cell, "hello world");
    expect(cell.textContent).toBe("hello world");
    // The stored inline LaTeX keeps an ordinary space, not a \nbsp ~.
    expect(stored()).toBe("hello world");
  });

  it("serializes a bold run (a <strong> tag) to \\textbf", () => {
    render(<Harness />);
    const cell = screen.getByRole("textbox");
    // Emulate what execCommand('bold') produces inside the cell.
    cell.innerHTML = "a<strong>b</strong>c";
    fireEvent.input(cell);
    expect(stored()).toBe("a\\textbf{b}c");
  });

  it("paints initial rich content and re-paints on external change", () => {
    const noop = vi.fn();
    const { rerender } = render(
      <RichCell value="\textbf{one}" ariaLabel="c" onChange={noop} />,
    );
    const cell = screen.getByRole("textbox");
    // Mount paint renders the bold as a <strong>, text "one".
    expect(cell.querySelector("strong")?.textContent).toBe("one");
    expect(cell.textContent).toBe("one");
    // An external value change (undo/redo) re-paints the DOM.
    rerender(<RichCell value="two" ariaLabel="c" onChange={noop} />);
    expect(cell.textContent).toBe("two");
    expect(cell.querySelector("strong")).toBeNull();
  });
});
