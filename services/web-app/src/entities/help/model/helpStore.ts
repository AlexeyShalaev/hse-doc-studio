import { create } from "zustand";

type HelpState = {
  isOpen: boolean;
  /** Был ли панель открыта хоть раз: до этого её чанк и карта справки не грузятся вовсе. */
  everOpened: boolean;
  /** Явная статья (значок у поля); без неё панель берёт статью текущего экрана. */
  articleKey?: string | undefined;
  /** Шаг (с единицы), к которому прокрутить и подсветить. */
  focusStep?: number | undefined;
};

type HelpActions = {
  open: (articleKey?: string, focusStep?: number) => void;
  close: () => void;
  toggle: () => void;
};

/**
 * Одна панель справки на всё приложение: кнопка в шапке, клавиша `?`, ⌘K и значки у полей
 * открывают один и тот же экземпляр, смонтированный в корневом макете.
 */
export const useHelpStore = create<HelpState & HelpActions>((set) => ({
  isOpen: false,
  everOpened: false,
  articleKey: undefined,
  focusStep: undefined,
  open: (articleKey, focusStep) => {
    set({ isOpen: true, everOpened: true, articleKey, focusStep });
  },
  close: () => {
    set({ isOpen: false, focusStep: undefined });
  },
  toggle: () => {
    set((state) =>
      state.isOpen
        ? { isOpen: false, focusStep: undefined }
        : {
            isOpen: true,
            everOpened: true,
            articleKey: undefined,
            focusStep: undefined,
          },
    );
  },
}));

export const openHelp = (articleKey?: string, focusStep?: number) => {
  useHelpStore.getState().open(articleKey, focusStep);
};
