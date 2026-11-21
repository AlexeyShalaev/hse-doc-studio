import { useEffect } from "react";
import { useLocation } from "react-router";

// Флаг нового интерфейса Студии шаблонов (pack-studio-ux.md, 8.3). Источник по убыванию:
// query `?ux=2` (или `?ux=1`, аварийный выход), память `localStorage` под ключом `ps.ux`,
// умолчание. Читается в одном месте, в `PackStudioApp`; срезы сами флаг не проверяют.

export type PackStudioUx = 1 | 2;

/** До среза S14 умолчание 1 (старый интерфейс); в S14 меняется на 2. */
export const PACK_STUDIO_UX_DEFAULT: PackStudioUx = 1;
export const PACK_STUDIO_UX_KEY = "ps.ux";

const parse = (value: string | null): PackStudioUx | null =>
  value === "1" ? 1 : value === "2" ? 2 : null;

// Хранилище может не открыться (частное окно): тогда выбор живёт, пока открыта вкладка.
let memory: PackStudioUx | null = null;

const readStored = (): PackStudioUx | null => {
  try {
    return parse(window.localStorage.getItem(PACK_STUDIO_UX_KEY)) ?? memory;
  } catch {
    return memory;
  }
};

const store = (ux: PackStudioUx): void => {
  memory = ux;
  try {
    window.localStorage.setItem(PACK_STUDIO_UX_KEY, String(ux));
  } catch {
    // Без хранилища выбор живёт в памяти вкладки.
  }
};

/** Сбросить память флага: нужно только тестам. */
export const resetPackStudioUx = (): void => {
  memory = null;
  try {
    window.localStorage.removeItem(PACK_STUDIO_UX_KEY);
  } catch {
    // нечего сбрасывать
  }
};

/** Какой интерфейс показывать: `2` новый, `1` прежний. Query запоминается на следующие заходы. */
export const usePackStudioUx = (): PackStudioUx => {
  const { search } = useLocation();
  const fromQuery = parse(new URLSearchParams(search).get("ux"));
  useEffect(() => {
    if (fromQuery) store(fromQuery);
  }, [fromQuery]);
  return fromQuery ?? readStored() ?? PACK_STUDIO_UX_DEFAULT;
};
