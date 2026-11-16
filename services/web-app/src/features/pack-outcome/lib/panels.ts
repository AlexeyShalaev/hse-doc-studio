import { useCallback, useState } from "react";
import { usePaneResize, type PaneResize } from "@shared/lib";

// Раскладка трёх колонок: ширина боковых панелей и свёрнутость хранятся в localStorage
// (template-studio-outcome.md, раздел 3.1). Без хранилища работают запасные значения.

const KEY = "hse-studio.packOutcome";

export const LEFT_PANEL = { default: 296, min: 232, max: 440 };
export const RIGHT_PANEL = { default: 344, min: 264, max: 560 };
/** Шаг кнопок «Шире» и «Уже»: крупнее шага стрелок, это замена перетаскиванию. */
export const PANEL_STEP = 32;

const readFlag = (key: string): boolean => {
  try {
    return window.localStorage.getItem(key) === "1";
  } catch {
    return false;
  }
};

export const useStoredFlag = (
  key: string,
): [boolean, (next: boolean) => void] => {
  const [value, setValue] = useState(() => readFlag(key));
  const set = useCallback(
    (next: boolean) => {
      setValue(next);
      try {
        window.localStorage.setItem(key, next ? "1" : "0");
      } catch {
        // Состояние живёт до перезагрузки.
      }
    },
    [key],
  );
  return [value, set];
};

export type OutcomePanels = {
  left: PaneResize;
  right: PaneResize;
  leftCollapsed: boolean;
  rightCollapsed: boolean;
  setLeftCollapsed: (next: boolean) => void;
  setRightCollapsed: (next: boolean) => void;
};

export const useOutcomePanels = (): OutcomePanels => {
  const left = usePaneResize({
    storageKey: `${KEY}.left`,
    defaultWidth: LEFT_PANEL.default,
    minWidth: LEFT_PANEL.min,
    maxWidth: LEFT_PANEL.max,
    direction: 1,
  });
  const right = usePaneResize({
    storageKey: `${KEY}.right`,
    defaultWidth: RIGHT_PANEL.default,
    minWidth: RIGHT_PANEL.min,
    maxWidth: RIGHT_PANEL.max,
    direction: -1,
  });
  const [leftCollapsed, setLeftCollapsed] = useStoredFlag(`${KEY}.left.off`);
  const [rightCollapsed, setRightCollapsed] = useStoredFlag(`${KEY}.right.off`);
  return {
    left,
    right,
    leftCollapsed,
    rightCollapsed,
    setLeftCollapsed,
    setRightCollapsed,
  };
};
