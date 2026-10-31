import { EditorState } from "@codemirror/state";
import { EditorView } from "@codemirror/view";
import { afterEach, describe, expect, it, vi } from "vitest";
import { createReviewBridge, setReviewMarks } from "./reviewMarks";

let view: EditorView | null = null;
afterEach(() => {
  view?.destroy();
  view = null;
});

const mount = (doc: string) => {
  const bridge = createReviewBridge();
  const host = document.createElement("div");
  document.body.append(host);
  view = new EditorView({
    state: EditorState.create({ doc, extensions: [bridge.extension] }),
    parent: host,
  });
  return { bridge, view };
};

const marked = (v: EditorView): string[] =>
  [...v.dom.querySelectorAll(".cm-review-mark")].map(
    (el) => el.textContent ?? "",
  );

describe("review marks", () => {
  it("highlights the fragments it is given and styles resolved and active ones", () => {
    const { view: v } = mount("Мы изучаем совместную правку текста.");

    v.dispatch({
      effects: setReviewMarks.of([
        { id: "a", from: 11, to: 28, resolved: false, active: true },
        { id: "b", from: 0, to: 2, resolved: true, active: false },
      ]),
    });

    expect(marked(v)).toEqual(["Мы", "совместную правку"]);
    expect(v.dom.querySelector(".cm-review-mark-resolved")?.textContent).toBe(
      "Мы",
    );
    expect(v.dom.querySelector(".cm-review-mark-active")?.textContent).toBe(
      "совместную правку",
    );
  });

  it("keeps marks on their text when the user types before them", () => {
    const { view: v } = mount("Мы изучаем совместную правку текста.");
    v.dispatch({
      effects: setReviewMarks.of([
        { id: "a", from: 11, to: 28, resolved: false, active: false },
      ]),
    });

    v.dispatch({ changes: { from: 0, insert: "Вставка. " } });

    expect(marked(v)).toEqual(["совместную правку"]);
  });

  it("opens the thread on click and starts a comment on the shortcut", () => {
    const { bridge, view: v } = mount("Текст для проверки.");
    const onSelect = vi.fn();
    const onComment = vi.fn();
    bridge.bind({ onSelect, onComment });
    v.dispatch({
      effects: setReviewMarks.of([
        { id: "t1", from: 0, to: 5, resolved: false, active: false },
      ]),
    });

    v.dom
      .querySelector<HTMLElement>("[data-review-thread]")
      ?.dispatchEvent(new MouseEvent("click", { bubbles: true }));
    v.contentDOM.dispatchEvent(
      new KeyboardEvent("keydown", {
        key: "M",
        code: "KeyM",
        keyCode: 77,
        shiftKey: true,
        ctrlKey: true,
        bubbles: true,
      }),
    );

    expect(onSelect).toHaveBeenCalledWith("t1");
    expect(onComment).toHaveBeenCalled();
  });
});
