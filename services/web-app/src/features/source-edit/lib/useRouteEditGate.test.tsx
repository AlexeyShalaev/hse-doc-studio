import { EditorSelection, EditorState } from "@codemirror/state";
import { EditorView } from "@codemirror/view";
import { act, cleanup, renderHook, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import * as Y from "yjs";
import { ySync, ySyncFacet, YSyncConfig } from "y-codemirror.next";
import { i18n } from "@shared/lib/i18n";
import {
  SR_DOC,
  SR_PROJECT_ID,
  makeSigningRouteSummary,
} from "@entities/signing-route/testing";
import { makeGuardHarness } from "@entities/signing-route/testing/guard";
import { useRouteEditGate } from "./useRouteEditGate";

// The `@shared/ui` barrel eagerly loads pdfjs-dist, which needs DOMMatrix.
vi.mock("pdfjs-dist", () => ({
  GlobalWorkerOptions: {},
  getDocument: () => ({ promise: Promise.resolve(null) }),
  version: "0",
}));

const views: EditorView[] = [];

// CodeMirror меряет текст в кадре анимации: у Range в jsdom нет геометрии.
const rangeProto = Range.prototype as Partial<
  Pick<Range, "getClientRects" | "getBoundingClientRect">
>;
rangeProto.getClientRects ??= () => [] as unknown as DOMRectList;
rangeProto.getBoundingClientRect ??= () => new DOMRect();

/** Редактор исходников с фильтром, как его собирает SourceEditor. */
const mountEditor = (path: string, doc = "\\section{Введение}") => {
  const harness = makeGuardHarness({
    routes: [makeSigningRouteSummary({ docs: [SR_DOC.doc_id] })],
  });
  const { result } = renderHook(() => useRouteEditGate(SR_PROJECT_ID, path), {
    wrapper: harness.wrapper,
  });
  const view = new EditorView({
    state: EditorState.create({
      doc,
      selection: EditorSelection.cursor(doc.length),
      extensions: result.current,
    }),
    parent: document.body,
  });
  views.push(view);
  return view;
};

const type = (view: EditorView, text: string) => {
  act(() => {
    view.dispatch(view.state.replaceSelection(text), {
      userEvent: "input.type",
    });
  });
};

describe("useRouteEditGate (source editor)", () => {
  beforeEach(async () => {
    await i18n.changeLanguage("ru");
  });
  afterEach(() => {
    for (const view of views.splice(0)) view.destroy();
    cleanup();
  });

  it("holds the first keystroke in a file of a document out for signing until continue", async () => {
    const user = userEvent.setup();
    const view = mountEditor(`${SR_DOC.doc_id}/sections/intro.tex`);

    type(view, "!");
    expect(view.state.doc.toString()).toBe("\\section{Введение}");
    expect(
      await screen.findByRole("dialog", { name: "Документ на подписании" }),
    ).toHaveTextContent(
      "Изменения не попадут в подписываемую версию. Продолжить?",
    );

    await user.click(screen.getByRole("button", { name: "Продолжить" }));
    expect(view.state.doc.toString()).toBe("\\section{Введение}!");

    type(view, "?");
    expect(view.state.doc.toString()).toBe("\\section{Введение}!?");
    expect(screen.queryByRole("dialog")).toBeNull();
  });

  it("leaves the text untouched on cancel", async () => {
    const user = userEvent.setup();
    const view = mountEditor(`${SR_DOC.doc_id}/${SR_DOC.doc_id}.tex`);
    type(view, "x");
    await user.click(await screen.findByRole("button", { name: "Отмена" }));
    expect(view.state.doc.toString()).toBe("\\section{Введение}");
  });

  it("lists the documents for a shared file", async () => {
    const view = mountEditor("common/refs.bib", "");
    type(view, "@book{");
    expect(await screen.findByRole("dialog")).toHaveTextContent(
      "Документ на подписании: Заявление о выборе темы.",
    );
  });

  it("does not ask in a document no route holds", () => {
    const view = mountEditor("supervisor_review/review.tex", "");
    type(view, "a");
    expect(view.state.doc.toString()).toBe("a");
    expect(screen.queryByRole("dialog")).toBeNull();
  });

  it("lets edits of collaborators through in a live session", () => {
    const harness = makeGuardHarness({
      routes: [makeSigningRouteSummary({ docs: [SR_DOC.doc_id] })],
    });
    const { result } = renderHook(
      () => useRouteEditGate(SR_PROJECT_ID, `${SR_DOC.doc_id}/a.tex`),
      { wrapper: harness.wrapper },
    );
    const ydoc = new Y.Doc();
    const text = ydoc.getText("t");
    const view = new EditorView({
      state: EditorState.create({
        doc: "",
        extensions: [
          ySyncFacet.of(new YSyncConfig(text, null)),
          ySync,
          result.current,
        ],
      }),
      parent: document.body,
    });
    views.push(view);
    act(() => {
      text.insert(0, "remote");
    });
    expect(view.state.doc.toString()).toBe("remote");
    expect(screen.queryByRole("dialog")).toBeNull();
  });
});
