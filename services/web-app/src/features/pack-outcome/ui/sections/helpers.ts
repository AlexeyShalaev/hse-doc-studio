import type { KeyboardEvent } from "react";
import type { OutcomeElementRef } from "@entities/pack-studio";
import { useOutcomeModel } from "../../model";

/** Выбран ли элемент: сравнение с `selected` из адреса. */
export const useIsSelected = (el: OutcomeElementRef): boolean => {
  const { url } = useOutcomeModel();
  const sel = url.state.selected;
  return sel !== null && sel.section === el.section && sel.id === el.id;
};

const isVisible = (el: HTMLElement) => el.closest("[hidden]") === null;

/**
 * Стрелки внутри секции: вверх и вниз переводят фокус по кнопкам выбора, Home и End к первой и
 * последней. Tab при этом работает как обычно: стрелки лишь ускоряют обход длинного списка.
 */
export const onArrowNav = (event: KeyboardEvent<HTMLElement>) => {
  const keys = ["ArrowDown", "ArrowUp", "Home", "End"];
  if (!keys.includes(event.key)) return;
  const target = event.target;
  if (!(target instanceof HTMLElement) || target.dataset.poPick !== "true") {
    return;
  }
  const all = Array.from(
    event.currentTarget.querySelectorAll<HTMLElement>("button[data-po-pick]"),
  ).filter(isVisible);
  const at = all.indexOf(target);
  if (at < 0) return;
  const next =
    event.key === "Home"
      ? 0
      : event.key === "End"
        ? all.length - 1
        : Math.min(
            all.length - 1,
            Math.max(0, at + (event.key === "ArrowDown" ? 1 : -1)),
          );
  event.preventDefault();
  all[next]?.focus();
};

/** Общий нормализатор поиска: без регистра, по подстроке. */
export const matches = (query: string, ...fields: (string | null)[]) => {
  const q = query.trim().toLowerCase();
  if (q === "") return true;
  return fields.some((f) => f?.toLowerCase().includes(q) === true);
};

/** Разложить элементы по группам в порядке первого появления группы. */
export const groupBy = <T>(
  items: readonly T[],
  key: (item: T) => string,
): [string, T[]][] => {
  const map = new Map<string, T[]>();
  for (const item of items) {
    const k = key(item);
    const list = map.get(k);
    if (list) list.push(item);
    else map.set(k, [item]);
  }
  return [...map.entries()];
};
