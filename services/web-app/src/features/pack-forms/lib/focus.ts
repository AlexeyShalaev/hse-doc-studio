import { useEffect, type RefObject } from "react";

// Переход к правилу из экрана «Результат»: вкладка «Форма» открывается на нужном разделе и
// выделяет запись манифеста по JSON Pointer. Записи форм помечены `data-pf-at="<указатель>"`;
// выбирается самая глубокая помеченная запись, на которую указывает правило, поэтому форма,
// не умеющая показать запись глубже, всё равно подсвечивает её владельца.

export type VersionSection =
  "fields" | "forms" | "documents" | "languages" | "submission" | "checks";

/** Раздел формы версии, где живёт запись по указателю `version.yaml`; без совпадения первый. */
export const sectionOfPointer = (
  pointer: string | null | undefined,
): VersionSection | null => {
  const head = pointer?.split("/")[1];
  switch (head) {
    case "meta_fields":
    case "meta_groups":
      return "fields";
    case "forms":
      return "forms";
    case "documents":
    case "dynamic_includes":
      return "documents";
    case "langs":
      return "languages";
    case "pack_submission":
    case "signatures":
      return "submission";
    case "checks_version":
      return "checks";
    default:
      return null;
  }
};

const FLASH_MS = 2600;
const WAIT_MS = 4000;

/** Самая глубокая запись, чей указатель совпадает с целью или является её предком. */
export const deepestRecord = (
  root: ParentNode,
  pointer: string,
): HTMLElement | null => {
  let best: HTMLElement | null = null;
  let bestLength = -1;
  for (const el of root.querySelectorAll<HTMLElement>("[data-pf-at]")) {
    const at = el.dataset.pfAt ?? "";
    const hit = pointer === at || pointer.startsWith(`${at}/`);
    if (hit && at.length > bestLength) {
      best = el;
      bestLength = at.length;
    }
  }
  return best;
};

/**
 * Выделить запись формы по указателю: прокрутка, фокус и обводка на пару секунд. Разделы грузятся
 * лениво, поэтому запись ищется, пока дерево меняется, но не дольше четырёх секунд.
 */
export const useRecordFocus = (
  root: RefObject<HTMLElement | null>,
  pointer: string | null | undefined,
  section: string,
): void => {
  useEffect(() => {
    const host = root.current;
    if (!host || !pointer) return undefined;
    let timer: ReturnType<typeof setTimeout> | undefined;
    let done = false;
    const reveal = (): boolean => {
      const el = deepestRecord(host, pointer);
      if (!el) return false;
      done = true;
      el.scrollIntoView({ block: "center" });
      el.tabIndex = -1;
      el.focus({ preventScroll: true });
      el.dataset.pfFlash = "true";
      timer = setTimeout(() => {
        delete el.dataset.pfFlash;
      }, FLASH_MS);
      return true;
    };
    if (reveal()) {
      return () => {
        if (timer) clearTimeout(timer);
      };
    }
    const observer = new MutationObserver(() => {
      if (!done && reveal()) observer.disconnect();
    });
    observer.observe(host, { childList: true, subtree: true });
    const giveUp = setTimeout(() => {
      observer.disconnect();
    }, WAIT_MS);
    return () => {
      observer.disconnect();
      clearTimeout(giveUp);
      if (timer) clearTimeout(timer);
    };
  }, [root, pointer, section]);
};
