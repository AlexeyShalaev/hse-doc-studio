import { useState } from "react";

// Черновик формы настроек поверх ответа сервера: хранятся только правки.
// Значение поля = правка ?? значение сервера, поэтому после сохранения
// достаточно сбросить правки, и форма показывает то, что вернул сервер.

export type Draft<T extends Record<string, unknown>> = {
  /** Текущие значения: сервер с наложенными правками. */
  value: T;
  /** Поля, которые отличаются от сервера (закрытые поля не считаются). */
  changed: (keyof T)[];
  isChanged: (key: keyof T) => boolean;
  set: (patch: Partial<T>) => void;
  reset: () => void;
};

export const useDraft = <T extends Record<string, unknown>>(
  base: T,
  editable: (key: keyof T) => boolean = () => true,
): Draft<T> => {
  const [edits, setEdits] = useState<Partial<T>>({});
  const value = { ...base, ...edits };
  const isChanged = (key: keyof T): boolean =>
    editable(key) && key in edits && !Object.is(edits[key], base[key]);
  return {
    value,
    changed: (Object.keys(base) as (keyof T)[]).filter(isChanged),
    isChanged,
    set: (patch) => {
      setEdits((prev) => ({ ...prev, ...patch }));
    },
    reset: () => {
      setEdits({});
    },
  };
};
