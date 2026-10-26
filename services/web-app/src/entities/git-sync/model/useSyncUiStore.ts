import { create } from "zustand";
import {
  createJSONStorage,
  persist,
  type StateStorage,
} from "zustand/middleware";

// Клиентское состояние синхронизации: что открыто и о чём уже сообщили.
// Всё, что приходит с сервера, живёт в запросах, а не здесь.
type SyncUiState = {
  // Всплывающая панель синхронизации в заголовке окна.
  popoverOpen: boolean;
  // Для каждого проекта: идентификатор последней синхронизации, о которой уже
  // сообщили тостом. Состояние сервера помнит итог и после перезагрузки страницы,
  // поэтому без этой отметки тост повторялся бы при каждом открытии проекта.
  toastedSyncIds: Record<string, string>;
};

type SyncUiActions = {
  setPopoverOpen: (open: boolean) => void;
  togglePopover: () => void;
  // true, если о синхронизации ещё не сообщали (и отмечает её сообщённой).
  claimSyncToast: (projectId: string, syncId: string) => boolean;
  forgetProject: (projectId: string) => void;
};

const safeLocalStorage: StateStorage = {
  getItem: (name) => {
    try {
      return localStorage.getItem(name);
    } catch {
      return null;
    }
  },
  setItem: (name, value) => {
    try {
      localStorage.setItem(name, value);
    } catch {
      // нет места или доступ закрыт: отметка просто не переживёт перезагрузку
    }
  },
  removeItem: (name) => {
    try {
      localStorage.removeItem(name);
    } catch {
      // см. выше
    }
  },
};

// Отметки о тостах хранятся ограниченно: на каждый проект один идентификатор.
const MAX_TRACKED_PROJECTS = 50;

export const useSyncUiStore = create<SyncUiState & SyncUiActions>()(
  persist(
    (set, get) => ({
      popoverOpen: false,
      toastedSyncIds: {},
      setPopoverOpen: (open) => {
        set({ popoverOpen: open });
      },
      togglePopover: () => {
        set({ popoverOpen: !get().popoverOpen });
      },
      claimSyncToast: (projectId, syncId) => {
        const current = get().toastedSyncIds;
        if (current[projectId] === syncId) return false;
        const entries = Object.entries({ ...current, [projectId]: syncId });
        set({
          toastedSyncIds: Object.fromEntries(
            entries.slice(-MAX_TRACKED_PROJECTS),
          ),
        });
        return true;
      },
      forgetProject: (projectId) => {
        const { [projectId]: _dropped, ...rest } = get().toastedSyncIds;
        set({ toastedSyncIds: rest });
      },
    }),
    {
      name: "hse-studio.gitSyncUi",
      // Хранилище может быть недоступно или переполнено (приватное окно): любой
      // сбой чтения и записи глотаем, интерфейс работает и без него.
      storage: createJSONStorage(() => safeLocalStorage),
      partialize: (state) => ({ toastedSyncIds: state.toastedSyncIds }),
    },
  ),
);
