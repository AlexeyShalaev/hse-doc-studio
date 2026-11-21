/** Параметр адреса: куда направить внимание при открытии панели «Изменения». */
export const FOCUS_PARAM = "focus";

/** `notes`: поле заметок («Описать изменения»); `submit`: кнопка отправки. */
export type FocusTarget = "notes" | "submit";

export const isFocusTarget = (value: string | null): value is FocusTarget =>
  value === "notes" || value === "submit";

/** Поле заметок («по-русски») и кнопка отправки: к ним ведут «Описать изменения» и «Отправить». */
export const NOTES_FIELD_ID = "sp-sb-notes-ru";
export const PRIMARY_BUTTON_ID = "sp-sb-primary";

/** Прокрутить к элементу и поставить на него фокус; `false`, если такого нет на экране. */
export const focusElement = (id: string): boolean => {
  const element = document.getElementById(id);
  if (!element) return false;
  // В jsdom (тесты) прокрутки нет.
  // eslint-disable-next-line @typescript-eslint/no-unnecessary-condition
  element.scrollIntoView?.({ block: "center" });
  element.focus({ preventScroll: true });
  return true;
};
