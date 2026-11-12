import { useEffect, useRef, useState } from "react";

// Запас у края, когда активная вкладка докручивается в видимую область: столько же
// занимает затухание `.scroll-hint`, иначе вкладка встала бы под него.
const EDGE_REM = 2;

const prefersReducedMotion = (): boolean =>
  typeof window.matchMedia === "function" &&
  window.matchMedia("(prefers-reduced-motion: reduce)").matches;

const setFlag = (el: HTMLElement, name: string, on: boolean): void => {
  if (on) el.setAttribute(name, "true");
  else el.removeAttribute(name);
};

/** Отмечает края, за которыми есть содержимое: по ним `.scroll-hint` рисует затухание. */
const markEdges = (el: HTMLElement): void => {
  const max = el.scrollWidth - el.clientWidth;
  setFlag(el, "data-scroll-start", el.scrollLeft > 1);
  setFlag(el, "data-scroll-end", max - el.scrollLeft > 1);
};

/** Докручивает строку так, чтобы активный элемент был виден целиком и не под затуханием. */
const revealActive = (
  el: HTMLElement,
  selector: string,
  smooth: boolean,
): void => {
  const target = el.querySelector<HTMLElement>(selector);
  if (!target || el.scrollWidth <= el.clientWidth) return;
  const rem = parseFloat(getComputedStyle(document.documentElement).fontSize);
  const edge = (Number.isFinite(rem) ? rem : 16) * EDGE_REM;
  const box = el.getBoundingClientRect();
  const rect = target.getBoundingClientRect();
  const left = rect.left - box.left + el.scrollLeft;
  const right = left + rect.width;
  let next: number | null = null;
  if (left - edge < el.scrollLeft) next = Math.max(0, left - edge);
  else if (right + edge > el.scrollLeft + el.clientWidth)
    next = right + edge - el.clientWidth;
  if (next === null) return;
  // scrollTo, а не scrollIntoView: тот прокрутил бы ещё и страницу по вертикали.
  el.scrollTo({ left: next, behavior: smooth ? "smooth" : "auto" });
};

/**
 * Строка вкладок, которая не помещается в ширину, прокручивается сама по себе
 * (docs/design/mobile-layout.md, раздел 9). Хук делает прокрутку заметной: ставит
 * `data-scroll-start` и `data-scroll-end` на края, за которыми что-то есть (класс
 * `scroll-hint` рисует там затухание), и при смене `activeKey` докручивает к
 * элементу `activeSelector`, чтобы выбранная вкладка не пряталась за краем экрана.
 *
 * Возвращает ref-функцию: строка может появиться позже первого рендера (документ
 * ещё грузится), обычный useRef её бы не заметил.
 */
export const useScrollHint = (
  activeKey: unknown,
  activeSelector = '[aria-selected="true"]',
): ((el: HTMLElement | null) => void) => {
  const [el, setEl] = useState<HTMLElement | null>(null);
  const revealedRef = useRef(false);

  useEffect(() => {
    if (el === null) return;
    const update = () => {
      markEdges(el);
    };
    update();
    el.addEventListener("scroll", update, { passive: true });
    let observer: ResizeObserver | undefined;
    if (typeof ResizeObserver === "function") {
      // Поворот экрана, подгрузка шрифта или перевода меняют ширины: выбранная
      // вкладка могла уехать за край, возвращаем её без анимации.
      observer = new ResizeObserver(() => {
        revealActive(el, activeSelector, false);
        update();
      });
      observer.observe(el);
      // Ширина содержимого меняется без смены ширины строки: счётчик замечаний, язык.
      for (const child of Array.from(el.children)) observer.observe(child);
    }
    return () => {
      el.removeEventListener("scroll", update);
      observer?.disconnect();
    };
  }, [el, activeSelector]);

  useEffect(() => {
    if (el === null) return;
    // Первый показ без анимации: строка сразу открывается на выбранной вкладке.
    revealActive(
      el,
      activeSelector,
      revealedRef.current && !prefersReducedMotion(),
    );
    revealedRef.current = true;
    markEdges(el);
  }, [el, activeKey, activeSelector]);

  return setEl;
};
