import { useCallback, useState } from "react";
import type { PreviewRunnerSeed } from "@features/pack-preview";
import { INPUTS_SOURCE, type PreviewSource } from "./previewRequest";

// Что экран «Результат» помнит о предпросмотре (срез F12).

const AUTO_KEY = "hse-studio.packOutcome.previewAuto";

const readAuto = (): boolean => {
  try {
    return window.sessionStorage.getItem(AUTO_KEY) === "1";
  } catch {
    return false;
  }
};

/**
 * Автосборка: переключатель живёт в sessionStorage (до закрытия вкладки), по умолчанию выключен.
 * В частном окне хранилище может не открыться: тогда выбор живёт до перезагрузки.
 */
export const useAutoPreview = (): [boolean, (next: boolean) => void] => {
  const [value, setValue] = useState(readAuto);
  const set = useCallback((next: boolean) => {
    setValue(next);
    try {
      window.sessionStorage.setItem(AUTO_KEY, next ? "1" : "0");
    } catch {
      // Без хранилища выбор живёт, пока открыт экран.
    }
  }, []);
  return [value, set];
};

/**
 * Состояние предпросмотра версии, которое переживает уход в «Файлы» и возврат: открытый документ,
 * источник вводных, выбранные варианты и последняя сборка. Живёт в памяти вкладки, на сервер и в
 * адрес не пишется.
 */
export type PreviewMemory = {
  document: string | null;
  source: PreviewSource;
  variants: Readonly<Record<string, string>>;
  built: PreviewRunnerSeed | null;
};

export const EMPTY_PREVIEW_MEMORY: PreviewMemory = {
  document: null,
  source: INPUTS_SOURCE,
  variants: {},
  built: null,
};

const memory = new Map<string, PreviewMemory>();

export const previewMemoryKey = (
  workspaceId: string,
  ref: { pack: string; template: string; version: string },
): string => `${workspaceId}:${ref.pack}/${ref.template}/${ref.version}`;

export const readPreviewMemory = (key: string): PreviewMemory =>
  memory.get(key) ?? EMPTY_PREVIEW_MEMORY;

export const writePreviewMemory = (
  key: string,
  patch: Partial<PreviewMemory>,
): void => {
  memory.set(key, { ...readPreviewMemory(key), ...patch });
};

/** Только для тестов: забыть предпросмотры всех версий. */
export const resetPreviewMemory = (): void => {
  memory.clear();
};
