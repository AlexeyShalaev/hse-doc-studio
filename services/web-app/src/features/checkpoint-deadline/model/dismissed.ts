import { useCallback, useState } from "react";

// «Не сейчас» у строки «Срок сдачи не указан» (docs/design/signing-route.md, 16.2): прячет
// мягкий запрос для этой точки в этом браузере. Указать срок можно и потом: кнопка остаётся.

const keyOf = (projectId: string, profileId: string): string =>
  `hse-studio.deadlinePrompt.${projectId}.${profileId}`;

export const isDeadlinePromptDismissed = (
  projectId: string,
  profileId: string,
): boolean => {
  try {
    return window.localStorage.getItem(keyOf(projectId, profileId)) === "1";
  } catch {
    // Хранилище закрыто (приватный режим): запрос показываем, это безопасная сторона.
    return false;
  }
};

export const dismissDeadlinePrompt = (
  projectId: string,
  profileId: string,
): void => {
  try {
    window.localStorage.setItem(keyOf(projectId, profileId), "1");
  } catch {
    // Не запомнилось: строка спрячется до перезагрузки страницы.
  }
};

/** Спрятан ли запрос срока у точки и как его спрятать (память вкладки, если хранилище закрыто). */
export const useDeadlinePromptDismissed = (
  projectId: string,
  profileId: string,
): [boolean, () => void] => {
  const [hidden, setHidden] = useState<Record<string, boolean>>({});
  const key = keyOf(projectId, profileId);
  const dismissed =
    hidden[key] ?? isDeadlinePromptDismissed(projectId, profileId);
  const dismiss = useCallback(() => {
    dismissDeadlinePrompt(projectId, profileId);
    setHidden((prev) => ({ ...prev, [key]: true }));
  }, [key, projectId, profileId]);
  return [dismissed, dismiss];
};
