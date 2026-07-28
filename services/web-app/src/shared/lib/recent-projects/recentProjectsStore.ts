import { useMemo } from "react";
import { create } from "zustand";
import { persist } from "zustand/middleware";

/** One visit: project id + when it was last opened (ms epoch). */
export type RecentProjectEntry = {
  id: string;
  at: number;
};

/** Hard cap on stored entries — the switcher never shows more than this. */
export const RECENT_PROJECTS_LIMIT = 12;

type RecentProjectsState = {
  /** Newest first, de-duplicated, at most RECENT_PROJECTS_LIMIT entries. */
  recent: RecentProjectEntry[];
};

type RecentProjectsActions = {
  /** Mark a project as just-opened: to the front, dropping the older visit. */
  touchProject: (projectId: string) => void;
  /** Drop a project (deleted/archived) so a dead id cannot linger forever. */
  forgetProject: (projectId: string) => void;
};

/**
 * "Недавние проекты" живут на клиенте, а не приходят с бэкенда, потому что
 * сортировать по `updated_at` нельзя: это mtime папки проекта, и он дёргается
 * при каждой компиляции (LaTeX пишет .build/ внутрь проекта). Карточки бы
 * прыгали местами от простого нажатия «Собрать», хотя пользователь ничего не
 * открывал. Здесь же порядок — это история навигации самого пользователя.
 */
export const useRecentProjectsStore = create<
  RecentProjectsState & RecentProjectsActions
>()(
  persist(
    (set) => ({
      recent: [],
      touchProject: (projectId: string) => {
        if (projectId === "") return;
        set((state) => ({
          recent: [
            { id: projectId, at: Date.now() },
            ...state.recent.filter((entry) => entry.id !== projectId),
          ].slice(0, RECENT_PROJECTS_LIMIT),
        }));
      },
      forgetProject: (projectId: string) => {
        set((state) => ({
          recent: state.recent.filter((entry) => entry.id !== projectId),
        }));
      },
    }),
    {
      name: "hse-studio.recentProjects",
      partialize: (state) => ({ recent: state.recent }),
    },
  ),
);

/** Ids of recently opened projects, newest first. */
export const useRecentProjectIds = (): string[] => {
  // Select the array by reference and derive ids in useMemo: zustand v5 would
  // warn about an unstable snapshot if the selector itself mapped the array.
  const recent = useRecentProjectsStore((state) => state.recent);
  return useMemo(() => recent.map((entry) => entry.id), [recent]);
};
