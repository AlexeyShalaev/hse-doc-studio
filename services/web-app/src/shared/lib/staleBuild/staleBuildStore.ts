import { create } from "zustand";

/** `chunk`: загрузка файла сборки не удалась; `version`: сервер сообщил о другой сборке. */
export type StaleReason = "chunk" | "version";

type StaleBuildState = {
  reason: StaleReason | null;
  /** Экран ошибки уже объясняет это сам, баннер поверх него не нужен. */
  screenShown: boolean;
  markStale: (reason: StaleReason) => void;
  setScreenShown: (shown: boolean) => void;
};

export const useStaleBuildStore = create<StaleBuildState>((set) => ({
  reason: null,
  screenShown: false,
  markStale: (reason) => {
    set((state) => ({ reason: state.reason ?? reason }));
  },
  setScreenShown: (shown) => {
    set({ screenShown: shown });
  },
}));
