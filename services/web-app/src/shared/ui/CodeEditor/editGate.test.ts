import { Annotation, EditorSelection, EditorState } from "@codemirror/state";
import { EditorView } from "@codemirror/view";
import { afterEach, describe, expect, it, vi } from "vitest";
import { createEditGate, editGate, type EditGate } from "./editGate";
import { externalDocumentSync } from "./visual/effects";

const remote = Annotation.define<boolean>();

/** Вопрос, на который тест отвечает сам. */
const deferredGate = (ask = true) => {
  let answer: (ok: boolean) => void = () => undefined;
  const gate: EditGate & { asked: number } = {
    asked: 0,
    shouldAsk: () => ask,
    ask: () => {
      gate.asked += 1;
      return new Promise<boolean>((resolve) => {
        answer = resolve;
      });
    },
  };
  return {
    gate,
    answer: async (ok: boolean) => {
      answer(ok);
      await flush();
    },
    stopAsking: () => {
      ask = false;
    },
  };
};

const flush = async () => {
  for (let i = 0; i < 3; i += 1) await Promise.resolve();
};

const views: EditorView[] = [];
const mount = (gate: EditGate, doc = "hello") => {
  const view = new EditorView({
    state: EditorState.create({
      doc,
      selection: EditorSelection.cursor(doc.length),
      extensions: editGate(gate, { exempt: [remote] }),
    }),
    parent: document.body,
  });
  views.push(view);
  return view;
};

/** Набор с клавиатуры: вставка в курсор, как делает CodeMirror. */
const type = (view: EditorView, text: string) => {
  view.dispatch(view.state.replaceSelection(text), {
    userEvent: "input.type",
  });
};

afterEach(() => {
  for (const view of views.splice(0)) view.destroy();
});

describe("editGate", () => {
  it("holds the first edit until the answer and applies it whole on continue", async () => {
    const { gate, answer, stopAsking } = deferredGate();
    const view = mount(gate);

    type(view, "!");
    expect(view.state.doc.toString()).toBe("hello");
    await flush();
    expect(gate.asked).toBe(1);

    stopAsking();
    await answer(true);
    expect(view.state.doc.toString()).toBe("hello!");
    expect(view.state.selection.main.head).toBe(6);

    type(view, "?");
    expect(view.state.doc.toString()).toBe("hello!?");
    expect(gate.asked).toBe(1);
  });

  it("leaves the text as it was on cancel", async () => {
    const { gate, answer } = deferredGate();
    const view = mount(gate);
    view.dispatch({
      changes: { from: 0, to: 5, insert: "bye" },
      userEvent: "delete",
    });
    await flush();
    await answer(false);
    expect(view.state.doc.toString()).toBe("hello");
    expect(view.state.selection.main.head).toBe(5);
  });

  it("keeps every keystroke typed before the answer, in order", async () => {
    const { gate, answer, stopAsking } = deferredGate();
    const view = mount(gate);
    type(view, "a");
    type(view, "b");
    view.dispatch({ changes: { from: 0, insert: ">" }, userEvent: "input" });
    await flush();
    expect(view.state.doc.toString()).toBe("hello");
    expect(gate.asked).toBe(1);

    stopAsking();
    await answer(true);
    expect(view.state.doc.toString()).toBe(">helloab");
  });

  it("lets collaborators' and host changes through and moves the held edit after them", async () => {
    const { gate, answer, stopAsking } = deferredGate();
    const view = mount(gate);
    type(view, "!");
    await flush();

    view.dispatch({
      changes: { from: 0, insert: "oh " },
      annotations: remote.of(true),
    });
    expect(view.state.doc.toString()).toBe("oh hello");

    stopAsking();
    await answer(true);
    expect(view.state.doc.toString()).toBe("oh hello!");
  });

  it("does not hold a controlled-value replacement from the host", () => {
    const { gate } = deferredGate();
    const view = mount(gate);
    view.dispatch({
      changes: { from: 0, to: 5, insert: "disk" },
      annotations: externalDocumentSync.of(true),
    });
    expect(view.state.doc.toString()).toBe("disk");
    expect(gate.asked).toBe(0);
  });

  it("passes edits straight through when there is nothing to ask", () => {
    const { gate } = deferredGate(false);
    const view = mount(gate);
    type(view, "!");
    expect(view.state.doc.toString()).toBe("hello!");
    expect(gate.asked).toBe(0);
  });

  it("does not touch selection-only transactions", () => {
    const { gate } = deferredGate();
    const view = mount(gate);
    view.dispatch({ selection: EditorSelection.cursor(1) });
    expect(view.state.selection.main.head).toBe(1);
    expect(gate.asked).toBe(0);
  });

  it("drops the held edit when the editor closes before the answer", async () => {
    const { gate, answer } = deferredGate();
    const view = mount(gate);
    type(view, "!");
    await flush();
    view.destroy();
    const dispatch = vi.spyOn(view, "dispatch");
    await answer(true);
    expect(dispatch).not.toHaveBeenCalled();
  });
});

describe("createEditGate", () => {
  it("asks nothing until a gate is bound, then asks the bound one", async () => {
    const bound = createEditGate();
    const view = new EditorView({
      state: EditorState.create({ doc: "x", extensions: bound.extension }),
      parent: document.body,
    });
    views.push(view);
    view.dispatch({ changes: { from: 1, insert: "1" }, userEvent: "input" });
    expect(view.state.doc.toString()).toBe("x1");

    const { gate, answer } = deferredGate();
    bound.bind(gate);
    view.dispatch({ changes: { from: 2, insert: "2" }, userEvent: "input" });
    expect(view.state.doc.toString()).toBe("x1");
    await flush();
    expect(gate.asked).toBe(1);
    await answer(false);
    expect(view.state.doc.toString()).toBe("x1");

    bound.bind(null);
    view.dispatch({ changes: { from: 2, insert: "3" }, userEvent: "input" });
    expect(view.state.doc.toString()).toBe("x13");
  });
});
