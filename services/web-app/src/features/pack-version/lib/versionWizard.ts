import type {
  PackLocalizedList,
  PackVersionState,
  UpdateClass,
} from "@entities/pack-studio";

export const UPDATE_CLASSES: readonly UpdateClass[] = [
  "patch",
  "minor",
  "major",
] as const;

const RANK: Record<UpdateClass, number> = { patch: 0, minor: 1, major: 2 };

/** `candidate` мягче `required`: patch мягче minor, minor мягче major. */
export const isSofter = (candidate: UpdateClass, required: UpdateClass) =>
  RANK[candidate] < RANK[required];

/** Пункты заметок в поле ввода: по строке на пункт. */
export const linesOf = (items: readonly string[]): string => items.join("\n");

/** Строки поля ввода в пункты: пустые строки и пробелы по краям убираются. */
export const itemsOf = (text: string): string[] =>
  text
    .split("\n")
    .map((line) => line.trim())
    .filter((line) => line !== "");

/** Заметки ru и en в виде, который ждёт сервер. */
export const notesOf = (ru: string, en: string): PackLocalizedList => ({
  ru: itemsOf(ru),
  en: itemsOf(en),
});

/** Списки ru и en одной длины (pack_lint проверяет, что пункты идут парами). */
export const notesParallel = (notes: PackLocalizedList): boolean =>
  notes.ru.length === notes.en.length;

/** Класс, который сейчас даёт номер черновика (по номеру, иначе по минимуму). */
export const currentClass = (state: PackVersionState): UpdateClass | null =>
  state.by_number ?? state.minimum;

/**
 * Нужно ли объяснение класса (`release.note`): номер мягче того, что предлагают
 * мягкие правила классификатора (template-studio.md, 7.2), но не мягче минимума.
 */
export const needsNote = (state: PackVersionState): boolean => {
  const chosen = currentClass(state);
  return (
    chosen !== null &&
    state.suggested !== null &&
    isSofter(chosen, state.suggested) &&
    (state.minimum === null || !isSofter(chosen, state.minimum))
  );
};
