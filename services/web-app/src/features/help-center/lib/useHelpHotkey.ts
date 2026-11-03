import { useEffect } from "react";

/**
 * `?` открывает справку по текущему экрану. Пока человек печатает (поле, textarea, contenteditable,
 * редактор CodeMirror), `?` остаётся обычным символом.
 */
export const isTypingTarget = (target: EventTarget | null): boolean => {
  if (!(target instanceof HTMLElement)) return false;
  if (target.isContentEditable) return true;
  const tag = target.tagName;
  if (tag === "INPUT" || tag === "TEXTAREA" || tag === "SELECT") return true;
  return target.closest(".cm-editor") !== null;
};

export const useHelpHotkey = (onOpen: () => void): void => {
  useEffect(() => {
    const onKeyDown = (event: KeyboardEvent) => {
      if (event.metaKey || event.ctrlKey || event.altKey) return;
      if (event.key !== "?") return;
      if (isTypingTarget(event.target)) return;
      event.preventDefault();
      onOpen();
    };
    document.addEventListener("keydown", onKeyDown);
    return () => {
      document.removeEventListener("keydown", onKeyDown);
    };
  }, [onOpen]);
};
