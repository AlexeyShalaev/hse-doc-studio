import type {
  PackVersionNotesRequest,
  PackVersionState,
  UpdateClass,
} from "@entities/pack-studio";
import {
  linesOf,
  needsNote,
  notesOf,
  notesParallel,
} from "@features/pack-version";

// Заметки к версии в поле ввода (pack-studio-ux.md, 5.6): те же `changes` ru и en, что у прежнего
// окна «Заметки», по пункту в строке. Чистые правила без React.

export type NotesDraft = {
  ru: string;
  en: string;
  breakingRu: string;
  breakingEn: string;
  note: string;
};

export const EMPTY_NOTES: NotesDraft = {
  ru: "",
  en: "",
  breakingRu: "",
  breakingEn: "",
  note: "",
};

/** Что уже записано в версии. */
export const notesFromState = (state: PackVersionState): NotesDraft => ({
  ru: linesOf(state.changes.ru),
  en: linesOf(state.changes.en),
  breakingRu: linesOf(state.breaking_changes.ru),
  breakingEn: linesOf(state.breaking_changes.en),
  note: state.note ?? "",
});

/** Подсказка по изменениям: черновик заметок из отчёта классификатора версии. */
export const notesSuggested = (state: PackVersionState): NotesDraft => ({
  ru: linesOf(state.draft_changes.ru),
  en: linesOf(state.draft_changes.en),
  breakingRu: linesOf(state.draft_breaking.ru),
  breakingEn: linesOf(state.draft_breaking.en),
  note: "",
});

/** Есть ли что подсказать (отчёт классификатора непустой). */
export const hasSuggestion = (state: PackVersionState): boolean =>
  state.draft_changes.ru.length > 0 || state.draft_breaking.ru.length > 0;

/** Блок «что перестанет работать»: нужен, если классификатор нашёл сужение или оно уже записано. */
export const showBreaking = (state: PackVersionState): boolean =>
  state.draft_breaking.ru.length > 0 ||
  state.breaking_changes.ru.length > 0 ||
  state.breaking_changes.en.length > 0;

/** Поле «почему номер мягче предложенного» нужно, когда номер мягче того, что подсказывают. */
export const showClassNote = (state: PackVersionState): boolean =>
  needsNote(state) || state.note !== null;

const norm = (text: string): string => notesOf(text, "").ru.join("\n");

/** Одинаковы ли заметки: пробелы и пустые строки не в счёт. */
export const sameNotes = (a: NotesDraft, b: NotesDraft): boolean =>
  norm(a.ru) === norm(b.ru) &&
  norm(a.en) === norm(b.en) &&
  norm(a.breakingRu) === norm(b.breakingRu) &&
  norm(a.breakingEn) === norm(b.breakingEn) &&
  a.note.trim() === b.note.trim();

/** Что значит неготовность заметок; `null`: можно отправлять. */
export type NotesProblem = "empty" | "pairs";

/**
 * Заметки годятся для записи: пункты на обоих языках есть и идут парами (проверка пака требует
 * одинаковой длины списков ru и en).
 */
export const notesProblem = (draft: NotesDraft): NotesProblem | null => {
  const changes = notesOf(draft.ru, draft.en);
  if (changes.ru.length === 0 || changes.en.length === 0) return "empty";
  if (!notesParallel(changes)) return "pairs";
  return notesParallel(notesOf(draft.breakingRu, draft.breakingEn))
    ? null
    : "pairs";
};

/** Тело записи заметок. Лишние блоки уходят, только если поля для них показаны. */
export const notesRequest = (
  draft: NotesDraft,
  show: { breaking: boolean; note: boolean },
): PackVersionNotesRequest => ({
  changes: notesOf(draft.ru, draft.en),
  ...(show.breaking
    ? { breaking_changes: notesOf(draft.breakingRu, draft.breakingEn) }
    : {}),
  ...(show.note ? { note: draft.note.trim() } : {}),
});

/** Как называем класс номера словами (раздел 6: patch, minor, major). */
export const CLASS_KEYS: Record<UpdateClass, string> = {
  patch: "small",
  minor: "features",
  major: "regulation",
};
