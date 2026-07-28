import { useCallback } from "react";
import { create } from "zustand";

// Ключ унаследован от рейки «Сдача»: один ключ на проект, а не общий блоб, —
// иначе уже сохранённые выборы авторов пропали бы при переезде на этот стор.
const STORAGE_PREFIX = "hse-studio.nav.author.";

const storageKey = (projectId: string): string =>
  `${STORAGE_PREFIX}${projectId}`;

// Читаем всё разом при загрузке модуля: дальше выбор — это обычное чтение из
// объекта, и экраны не расходятся из-за ленивой догрузки в разные моменты.
const readStoredAuthors = (): Record<string, string> => {
  const stored: Record<string, string> = {};
  try {
    for (let i = 0; i < window.localStorage.length; i += 1) {
      const key = window.localStorage.key(i);
      if (key?.startsWith(STORAGE_PREFIX) !== true) continue;
      const value = window.localStorage.getItem(key);
      if (value != null && value !== "") {
        stored[key.slice(STORAGE_PREFIX.length)] = value;
      }
    }
  } catch {
    // Приватный режим / переполненное хранилище: выбор автора — удобство, а не
    // данные, поэтому молча начинаем с пустой памяти.
  }
  return stored;
};

const writeStoredAuthor = (projectId: string, slug: string | null): void => {
  try {
    if (slug == null || slug === "") {
      window.localStorage.removeItem(storageKey(projectId));
    } else {
      window.localStorage.setItem(storageKey(projectId), slug);
    }
  } catch {
    // См. readStoredAuthors.
  }
};

export type SubmissionAuthorState = {
  /** projectId → slug выбранного автора; проекта нет в словаре — выбора не было. */
  selectedAuthorBy: Record<string, string>;
};

export type SubmissionAuthorActions = {
  setSelectedAuthor: (projectId: string, slug: string | null) => void;
};

/**
 * Общий выбор «чей пакет собираем».
 *
 * Экран контрольной точки, панель «Сдача» и экран упаковки — соседи, а не
 * родитель с ребёнком, и раньше каждый держал выбор автора у себя. Из-за этого
 * студент мог прочитать «Готово 12 из 12» про Иванова и собрать пакет Шалаева.
 * Стор в shared — единственное место, где этот выбор живёт; localStorage лишь
 * его долговременная копия.
 */
export const useSubmissionAuthorStore = create<
  SubmissionAuthorState & SubmissionAuthorActions
>()((set) => ({
  selectedAuthorBy: readStoredAuthors(),
  setSelectedAuthor: (projectId: string, slug: string | null) => {
    if (projectId === "") return;
    writeStoredAuthor(projectId, slug);
    set((state) => {
      const rest = Object.fromEntries(
        Object.entries(state.selectedAuthorBy).filter(
          ([id]) => id !== projectId,
        ),
      );
      return {
        selectedAuthorBy:
          slug == null || slug === "" ? rest : { ...rest, [projectId]: slug },
      };
    });
  },
}));

/**
 * Автор, на которого считается готовность и собирается пакет.
 *
 * Сохранённый slug мог исчезнуть вместе с правкой состава команды — тогда
 * выбор откатывается на первого управляемого автора, а не пропадает совсем:
 * пакет всегда собирается на кого-то конкретного.
 */
export const resolveSelectedAuthorSlug = (
  storedSlug: string | null | undefined,
  authorSlugs: readonly string[],
): string | null => {
  if (storedSlug != null && authorSlugs.includes(storedSlug)) return storedSlug;
  return authorSlugs[0] ?? null;
};

export type SubmissionAuthorSelection = {
  /** null — выбирать не из кого (одиночный проект или нет управляемых папок). */
  selectedAuthorSlug: string | null;
  setSelectedAuthorSlug: (slug: string | null) => void;
};

/** Выбор автора для проекта с откатом на первого из `authorSlugs`. */
export const useSubmissionAuthor = (
  projectId: string,
  authorSlugs: readonly string[],
): SubmissionAuthorSelection => {
  const storedSlug = useSubmissionAuthorStore(
    (state) => state.selectedAuthorBy[projectId] ?? null,
  );
  const setSelectedAuthor = useSubmissionAuthorStore(
    (state) => state.setSelectedAuthor,
  );

  const setSelectedAuthorSlug = useCallback(
    (slug: string | null): void => {
      setSelectedAuthor(projectId, slug);
    },
    [projectId, setSelectedAuthor],
  );

  return {
    selectedAuthorSlug: resolveSelectedAuthorSlug(storedSlug, authorSlugs),
    setSelectedAuthorSlug,
  };
};
