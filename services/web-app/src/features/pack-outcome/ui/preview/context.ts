import { createContext, useContext } from "react";

/**
 * Предпросмотр PDF документа на экране «Результат» (срез F12). Секция «Документы» открывает его
 * из контекста: панель и сборка живут в `PreviewHost`, секциям они не нужны.
 */
export type PreviewUi = {
  /** Открыть предпросмотр документа и собрать его (явное действие человека). */
  open: (document: string) => void;
  close: () => void;
  /** Документ, чей предпросмотр открыт. */
  document: string | null;
  /** Предпросмотр собирает рабочее дерево и нужен автору: иначе кнопка скрыта или отключена. */
  available: boolean;
  /** Почему недоступен: режим «Как студент» (кнопки нет) или версия не из рабочего дерева. */
  unavailableReason: "student" | "state" | null;
};

export const PreviewUiContext = createContext<PreviewUi | null>(null);

/** Предпросмотр экрана; вне экрана «Результат» его нет. */
export const usePreviewUi = (): PreviewUi | null =>
  useContext(PreviewUiContext);
