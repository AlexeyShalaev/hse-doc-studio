import { useEffect, useState } from "react";
import type { Rect, Viewport } from "./placement";

const readViewport = (): Viewport => ({
  width: window.innerWidth,
  height: window.innerHeight,
});

const sameRect = (a: Rect | null, b: Rect | null): boolean =>
  a === b ||
  (a !== null &&
    b !== null &&
    Math.abs(a.top - b.top) < 0.5 &&
    Math.abs(a.left - b.left) < 0.5 &&
    Math.abs(a.width - b.width) < 0.5 &&
    Math.abs(a.height - b.height) < 0.5);

const visible = (el: Element): boolean => {
  const r = el.getBoundingClientRect();
  return r.width > 0 && r.height > 0;
};

/**
 * Положение элемента по селектору: следит за прокруткой, сменой размера окна и
 * появлением или исчезновением элемента. Нет элемента (или он скрыт) — `null`.
 */
export const useTargetRect = (
  selector: string | undefined,
): { rect: Rect | null; viewport: Viewport } => {
  const [state, setState] = useState<{ rect: Rect | null; viewport: Viewport }>(
    () => ({ rect: null, viewport: readViewport() }),
  );

  useEffect(() => {
    let frame = 0;
    let scrolled = false;
    const measure = () => {
      frame = 0;
      const el = selector ? document.querySelector(selector) : null;
      const found = el && visible(el) ? el : null;
      if (found && !scrolled) {
        scrolled = true;
        const r = found.getBoundingClientRect();
        if (r.top < 0 || r.bottom > window.innerHeight) {
          found.scrollIntoView({ block: "center", inline: "nearest" });
        }
      }
      const r = found?.getBoundingClientRect();
      const rect = r
        ? { top: r.top, left: r.left, width: r.width, height: r.height }
        : null;
      const viewport = readViewport();
      setState((prev) =>
        sameRect(prev.rect, rect) &&
        prev.viewport.width === viewport.width &&
        prev.viewport.height === viewport.height
          ? prev
          : { rect, viewport },
      );
    };
    const schedule = () => {
      if (frame === 0) frame = requestAnimationFrame(measure);
    };
    measure();
    window.addEventListener("resize", schedule);
    window.addEventListener("scroll", schedule, true);
    const mutations = new MutationObserver(schedule);
    mutations.observe(document.body, {
      childList: true,
      subtree: true,
      attributes: true,
      attributeFilter: ["class", "style", "hidden", "data-tour"],
    });
    const sizes =
      typeof ResizeObserver === "undefined"
        ? null
        : new ResizeObserver(schedule);
    sizes?.observe(document.body);
    return () => {
      if (frame !== 0) cancelAnimationFrame(frame);
      window.removeEventListener("resize", schedule);
      window.removeEventListener("scroll", schedule, true);
      mutations.disconnect();
      sizes?.disconnect();
    };
  }, [selector]);

  return state;
};
