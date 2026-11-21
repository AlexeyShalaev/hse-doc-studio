const KEY = "ps.lastWorkspace";

/** Пространство, которое человек открывал последним (только удобство, без него «Продолжить» не предлагается). */
export const readLastOpened = (): string | null => {
  try {
    return window.localStorage.getItem(KEY);
  } catch {
    return null;
  }
};

export const writeLastOpened = (id: string): void => {
  try {
    window.localStorage.setItem(KEY, id);
  } catch {
    // Хранилище недоступно (приватный режим): «Продолжить» просто не появится.
  }
};
