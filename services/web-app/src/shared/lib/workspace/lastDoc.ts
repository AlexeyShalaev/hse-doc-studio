/**
 * Last document opened per project — «вернуть человека туда, где он был».
 * /projects/:id читает это ровно один раз во время редиректа, поэтому здесь
 * намеренно нет zustand: подписка на стор ради одного чтения на переходе
 * означала бы лишние ре-рендеры всего дерева при каждой смене документа.
 */

const lastDocKey = (projectId: string): string =>
  `hse-studio.lastDoc.${projectId}`;

/** Document id the user last had open in this project, or null if unknown. */
export const getLastDoc = (projectId: string): string | null => {
  if (projectId === "") return null;
  try {
    const stored = window.localStorage.getItem(lastDocKey(projectId));
    // Empty string == no memory: an empty doc id would redirect to nowhere.
    return stored === null || stored === "" ? null : stored;
  } catch {
    // Private mode / disabled storage — навигация важнее памяти о документе.
    return null;
  }
};

/** Called when a project is deleted so its key does not outlive the project. */
export const forgetLastDoc = (projectId: string): void => {
  if (projectId === "") return;
  try {
    window.localStorage.removeItem(lastDocKey(projectId));
  } catch {
    // ignore
  }
};

export const setLastDoc = (projectId: string, docId: string): void => {
  if (projectId === "") return;
  // An empty doc id would be stored and then read back as "no memory" anyway.
  if (docId === "") {
    forgetLastDoc(projectId);
    return;
  }
  try {
    window.localStorage.setItem(lastDocKey(projectId), docId);
  } catch {
    // Quota — remembering the position is best-effort.
  }
};
