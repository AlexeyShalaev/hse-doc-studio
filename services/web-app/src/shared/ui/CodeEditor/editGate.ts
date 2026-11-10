import {
  Annotation,
  EditorState,
  type ChangeSet,
  type EditorSelection,
  Transaction,
  type AnnotationType,
  type Extension,
} from "@codemirror/state";
import { ViewPlugin, type EditorView } from "@codemirror/view";
import { externalDocumentSync } from "./visual/effects";

/**
 * Вопрос перед первой правкой текста. `shouldAsk` читается синхронно на каждую правку, `ask`
 * показывает вопрос и отвечает, можно ли применить правку.
 */
export type EditGate = {
  shouldAsk: () => boolean;
  ask: () => Promise<boolean>;
};

export type EditGateOptions = {
  /** Правки с этими аннотациями приходят не от человека (совместная правка): их не держим. */
  exempt?: readonly AnnotationType<unknown>[];
};

/** Повтор придержанной правки после «Продолжить»: фильтр её пропускает. */
const gatePass = Annotation.define<boolean>();

type Held = {
  changes: ChangeSet;
  selection: EditorSelection;
  /** Единственная придержанная правка без чужих правок поверх: её повторяем как есть. */
  only: Transaction | null;
};

/**
 * Фильтр транзакций до применения: первая правка, на которую `gate` хочет спросить, не
 * применяется, пока человек не ответит. «Продолжить» применяет её (и всё, что успели набрать,
 * пока открывалось окно) одной транзакцией, «Отмена» оставляет текст как был. Полправки не
 * бывает: транзакция либо целиком придержана, либо целиком применена.
 */
export const editGate = (
  gate: EditGate,
  { exempt = [] }: EditGateOptions = {},
): Extension => {
  let view: EditorView | null = null;
  let held: Held | null = null;

  const isExempt = (tr: Transaction): boolean =>
    tr.annotation(gatePass) === true ||
    tr.annotation(externalDocumentSync) === true ||
    exempt.some((type) => tr.annotation(type) !== undefined);

  const release = (ok: boolean) => {
    const current = held;
    held = null;
    if (!ok || current === null || view === null) return;
    const { only } = current;
    const userEvent = only?.annotation(Transaction.userEvent) ?? "input";
    // Одна правка повторяется со своим выделением и эффектами; сложенная ставит курсор за
    // вставленный текст.
    const selection = only
      ? only.selection
      : current.selection.map(current.changes, 1);
    view.dispatch({
      changes: current.changes,
      ...(selection ? { selection } : {}),
      ...(only ? { effects: only.effects } : {}),
      scrollIntoView: true,
      annotations: [gatePass.of(true), Transaction.userEvent.of(userEvent)],
    });
  };

  const filter = EditorState.transactionFilter.of((tr) => {
    if (!tr.docChanged) return tr;
    if (isExempt(tr)) {
      // Чужая правка пришла, пока окно открыто: придержанное сдвигаем вслед за ней.
      if (held !== null) {
        held = {
          changes: held.changes.map(tr.changes),
          selection: held.selection.map(tr.changes),
          only: null,
        };
      }
      return tr;
    }
    if (held !== null) {
      // Окно ещё не ответило: набранное копим, чтобы не потерять ни одного нажатия.
      const next = tr.changes.map(held.changes);
      held = {
        changes: held.changes.compose(next),
        selection: held.selection,
        only: null,
      };
      return [];
    }
    if (!gate.shouldAsk()) return tr;
    held = {
      changes: tr.changes,
      selection: tr.startState.selection,
      only: tr,
    };
    // Окно открываем после текущей транзакции: фильтр не должен трогать состояние React.
    queueMicrotask(() => {
      gate.ask().then(release, () => {
        release(false);
      });
    });
    return [];
  });

  const owner = ViewPlugin.define((v) => {
    view = v;
    return {
      destroy: () => {
        view = null;
        held = null;
      },
    };
  });

  return [filter, owner];
};

/** Фильтр, вопрос к которому привязывают позже: расширение создаётся с редактором один раз. */
export type BoundEditGate = {
  extension: Extension;
  /** Новый вопрос; null: не спрашивать. */
  bind: (gate: EditGate | null) => void;
};

export const createEditGate = (
  options: EditGateOptions = {},
): BoundEditGate => {
  let current: EditGate | null = null;
  return {
    extension: editGate(
      {
        shouldAsk: () => current?.shouldAsk() ?? false,
        ask: () => current?.ask() ?? Promise.resolve(true),
      },
      options,
    ),
    bind: (gate) => {
      current = gate;
    },
  };
};
