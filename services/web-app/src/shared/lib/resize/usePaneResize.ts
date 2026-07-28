import { useCallback, useState, type PointerEvent } from "react";

const clamp = (value: number, min: number, max: number): number =>
  Math.min(Math.max(value, min), max);

const readStoredWidth = (
  key: string,
  fallback: number,
  min: number,
  max: number,
): number => {
  const raw = window.localStorage.getItem(key);
  const parsed = raw === null ? Number.NaN : Number.parseInt(raw, 10);
  return Number.isFinite(parsed) ? clamp(parsed, min, max) : fallback;
};

export type PaneResizeConfig = {
  storageKey: string;
  defaultWidth: number;
  minWidth: number;
  maxWidth: number;
  // Where the drag handle sits relative to the pane it sizes:
  //   1  → handle on the RIGHT/BOTTOM of the pane (drag right/down widens,
  //        e.g. a left nav)
  //  -1  → handle on the LEFT/TOP of the pane (drag left/up widens, e.g. a
  //        right chat, a bottom dock)
  direction: 1 | -1;
  // Drag axis: "x" sizes a pane's width (default), "y" its height. Only the
  // pointer coordinate and the body cursor differ — clamping, persistence and
  // keyboard nudging are identical, so `width` carries the height for "y".
  axis?: "x" | "y";
};

export type PaneResize = {
  width: number;
  isResizing: boolean;
  setWidth: (next: number) => void;
  reset: () => void;
  nudge: (delta: number) => void;
  startResize: (event: PointerEvent<HTMLDivElement>) => void;
};

// Drag-to-resize for a single docked pane: clamped width persisted to
// localStorage, pointer-drag with global cursor/selection guards, plus
// keyboard nudge and double-click reset. Direction- and axis-aware so the same
// hook drives a left-docked nav, a right-docked chat and a bottom dock.
export const usePaneResize = ({
  storageKey,
  defaultWidth,
  minWidth,
  maxWidth,
  direction,
  axis = "x",
}: PaneResizeConfig): PaneResize => {
  const [width, setWidthState] = useState(() =>
    readStoredWidth(storageKey, defaultWidth, minWidth, maxWidth),
  );
  const [isResizing, setIsResizing] = useState(false);

  const setWidth = useCallback(
    (next: number) => {
      const clamped = clamp(next, minWidth, maxWidth);
      setWidthState(clamped);
      window.localStorage.setItem(storageKey, clamped.toString());
    },
    [storageKey, minWidth, maxWidth],
  );

  const reset = useCallback(() => {
    setWidth(defaultWidth);
  }, [setWidth, defaultWidth]);

  const nudge = useCallback(
    (delta: number) => {
      setWidth(width + delta * direction);
    },
    [setWidth, width, direction],
  );

  const startResize = useCallback(
    (event: PointerEvent<HTMLDivElement>) => {
      event.preventDefault();
      const isVertical = axis === "y";
      const start = isVertical ? event.clientY : event.clientX;
      const startWidth = width;
      const previousCursor = document.body.style.cursor;
      const previousUserSelect = document.body.style.userSelect;

      setIsResizing(true);
      document.body.style.cursor = isVertical ? "row-resize" : "col-resize";
      document.body.style.userSelect = "none";

      const handleMove = (moveEvent: globalThis.PointerEvent) => {
        const position = isVertical ? moveEvent.clientY : moveEvent.clientX;
        const delta = (position - start) * direction;
        setWidth(startWidth + delta);
      };

      const stopResize = () => {
        setIsResizing(false);
        document.body.style.cursor = previousCursor;
        document.body.style.userSelect = previousUserSelect;
        window.removeEventListener("pointermove", handleMove);
        window.removeEventListener("pointerup", stopResize);
        window.removeEventListener("pointercancel", stopResize);
      };

      window.addEventListener("pointermove", handleMove);
      window.addEventListener("pointerup", stopResize);
      window.addEventListener("pointercancel", stopResize);
    },
    [width, direction, axis, setWidth],
  );

  return { width, isResizing, setWidth, reset, nudge, startResize };
};
