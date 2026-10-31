import { StateEffect, StateField, type Extension } from "@codemirror/state";
import {
  Decoration,
  EditorView,
  keymap,
  type DecorationSet,
} from "@codemirror/view";

// Подсветка комментируемых фрагментов в CodeMirror. Позиции приходят из resolveAnchor
// (entities/review) и между пересчётами сдвигаются вместе с правками (decorations.map),
// поэтому метки не прыгают, пока человек печатает.

export type ReviewMark = {
  id: string;
  from: number;
  to: number;
  resolved: boolean;
  active: boolean;
};

export const setReviewMarks = StateEffect.define<ReviewMark[]>();

const buildDecorations = (marks: ReviewMark[], length: number): DecorationSet =>
  Decoration.set(
    marks
      .filter((m) => m.from < m.to && m.to <= length)
      .map((m) =>
        Decoration.mark({
          class: [
            "cm-review-mark",
            m.resolved ? "cm-review-mark-resolved" : "",
            m.active ? "cm-review-mark-active" : "",
          ]
            .filter(Boolean)
            .join(" "),
          attributes: { "data-review-thread": m.id },
        }).range(m.from, m.to),
      ),
    true,
  );

const marksField = StateField.define<DecorationSet>({
  create: () => Decoration.none,
  update(value, tr) {
    let next = value.map(tr.changes);
    for (const effect of tr.effects) {
      if (effect.is(setReviewMarks)) {
        next = buildDecorations(effect.value, tr.state.doc.length);
      }
    }
    return next;
  },
  provide: (field) => EditorView.decorations.from(field),
});

const theme = EditorView.baseTheme({
  ".cm-review-mark": {
    backgroundColor: "color-mix(in srgb, var(--c-warn) 26%, transparent)",
    borderBottom: "2px solid var(--c-warn)",
    cursor: "pointer",
  },
  ".cm-review-mark-resolved": {
    backgroundColor: "color-mix(in srgb, var(--fg-3) 14%, transparent)",
    borderBottomColor: "var(--fg-3)",
    borderBottomStyle: "dotted",
  },
  ".cm-review-mark-active": {
    backgroundColor: "color-mix(in srgb, var(--accent) 30%, transparent)",
    borderBottomColor: "var(--accent)",
  },
});

export type ReviewMarksHandlers = {
  onSelect: (threadId: string) => void;
  onComment: () => void;
};

export type ReviewBridge = {
  extension: Extension;
  /** Подключает обработчики хоста: расширение создаётся раньше редактора, обработчики появляются позже. */
  bind: (handlers: ReviewMarksHandlers) => void;
};

/** Подсветка, клик по фрагменту открывает тред, Mod-Shift-m начинает комментарий к выделению. */
export const createReviewBridge = (): ReviewBridge => {
  let current: ReviewMarksHandlers | null = null;
  const extension: Extension = [
    marksField,
    theme,
    EditorView.domEventHandlers({
      click: (event) => {
        const target = event.target instanceof Element ? event.target : null;
        const id = target?.closest<HTMLElement>("[data-review-thread]")?.dataset
          .reviewThread;
        if (id) current?.onSelect(id);
        return false;
      },
    }),
    keymap.of([
      {
        key: "Mod-Shift-m",
        run: () => {
          current?.onComment();
          return true;
        },
      },
    ]),
  ];
  return {
    extension,
    bind: (handlers) => {
      current = handlers;
    },
  };
};
