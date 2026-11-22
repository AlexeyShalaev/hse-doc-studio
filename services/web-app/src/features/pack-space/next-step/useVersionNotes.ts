import { useEffect, useEffectEvent, useState } from "react";
import {
  notifyPackFilesSaved,
  useSavePackVersionNotes,
  type PackVersionState,
} from "@entities/pack-studio";
import {
  EMPTY_NOTES,
  notesFromState,
  notesProblem,
  notesRequest,
  notesSuggested,
  hasSuggestion,
  sameNotes,
  showBreaking,
  showClassNote,
  type NotesDraft,
  type NotesProblem,
} from "./notesDraft";

/** Через сколько после последней правки заметки записываются сами. */
export const NOTES_AUTOSAVE_MS = 1200;

export type VersionNotes = {
  draft: NotesDraft;
  set: (key: keyof NotesDraft, value: string) => void;
  /** Заполнить из отчёта классификатора (кнопка «Подсказать по изменениям»). */
  suggest: () => void;
  canSuggest: boolean;
  /**
   * Заметки пусты, а подсказка по изменениям есть и годится как есть: при отправке Студия
   * подставит её сама, и отдельный шаг «Подсказать» не нужен.
   */
  canAutoFill: boolean;
  /** Записать подсказку в версию (шаг отправки, когда заметки пусты). */
  fillSuggested: () => Promise<void>;
  /** Показывать поля «что перестанет работать» и «почему такой номер». */
  breaking: boolean;
  classNote: boolean;
  problem: NotesProblem | null;
  /** Заметки на экране отличаются от записанных в версию. */
  pending: boolean;
  saving: boolean;
  /** Записано в версию (после последней правки). */
  saved: boolean;
  error: unknown;
  /** Записать сейчас, если есть что и это можно. Шаг отправки ждёт её. */
  flush: () => Promise<void>;
};

/**
 * Заметки открытой версии в поле ввода: черновик из записанного в версии, автозапись через
 * 1,2 секунды после правки (когда пункты есть на обоих языках и идут парами) и немедленная
 * запись по `flush`. `state` это отчёт версии (`usePackVersionState`); `null`: версия не
 * черновик или отчёт ещё не пришёл, полей нет.
 */
export const useVersionNotes = (
  workspaceId: string,
  state: PackVersionState | null,
): VersionNotes => {
  const save = useSavePackVersionNotes(workspaceId);
  const key = state ? state.version.path : null;
  const [draft, setDraft] = useState<NotesDraft>(EMPTY_NOTES);
  const [seeded, setSeeded] = useState<string | null>(null);
  // Записанное этим хуком: отчёт версии догонит его после перечитывания.
  const [written, setWritten] = useState<NotesDraft | null>(null);
  const [writtenFor, setWrittenFor] = useState<PackVersionState | null>(null);

  // Версия открыта (или сменилась): поля берут то, что записано в ней. Состояние от пропа без
  // эффекта, как в прежних окнах.
  if (state && key !== seeded) {
    setSeeded(key);
    setDraft(notesFromState(state));
    setWritten(null);
  }
  // Пришёл свежий отчёт: он уже знает наши записи.
  if (state !== writtenFor) {
    setWrittenFor(state);
    if (written !== null) setWritten(null);
  }

  const stored = written ?? (state ? notesFromState(state) : EMPTY_NOTES);
  const problem = state ? notesProblem(draft) : null;
  const pending = state !== null && !sameNotes(draft, stored);
  const breaking = state !== null && showBreaking(state);
  const classNote = state !== null && showClassNote(state);

  const suggested = state ? notesSuggested(state) : null;
  const canAutoFill =
    state !== null &&
    suggested !== null &&
    problem === "empty" &&
    hasSuggestion(state) &&
    notesProblem(suggested) === null;

  const saveAsync = save.mutateAsync;
  const fillSuggested = async (): Promise<void> => {
    if (!state || !suggested || !canAutoFill) return;
    setDraft(suggested);
    await saveAsync({
      ref: state.version,
      body: notesRequest(suggested, { breaking, note: classNote }),
    });
    setWritten(suggested);
    notifyPackFilesSaved(workspaceId);
  };
  const flush = async (): Promise<void> => {
    if (!state || problem !== null || !pending) return;
    await saveAsync({
      ref: state.version,
      body: notesRequest(draft, { breaking, note: classNote }),
    });
    setWritten(draft);
    notifyPackFilesSaved(workspaceId);
  };
  const autosave = useEffectEvent(() => {
    void flush().catch(() => undefined);
  });

  // Автозапись: тихо, без окна. Повтор тех же слов не пишет (`pending` снимается записью).
  useEffect(() => {
    if (!pending || problem !== null || save.isPending) return;
    const timer = setTimeout(autosave, NOTES_AUTOSAVE_MS);
    return () => {
      clearTimeout(timer);
    };
  }, [pending, problem, save.isPending, draft]);

  return {
    draft,
    set: (field, value) => {
      setDraft((prev) => ({ ...prev, [field]: value }));
    },
    suggest: () => {
      if (!state) return;
      const { ru, en, breakingRu, breakingEn } = notesSuggested(state);
      setDraft((prev) => ({ ...prev, ru, en, breakingRu, breakingEn }));
    },
    canSuggest: state !== null && hasSuggestion(state),
    canAutoFill,
    fillSuggested,
    breaking,
    classNote,
    problem,
    pending,
    saving: save.isPending,
    saved: state !== null && !pending && problem === null,
    error: save.error,
    flush,
  };
};
