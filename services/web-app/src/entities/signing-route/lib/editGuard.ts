import type { SigningRouteSummary } from "../model/signingRoute.schema";

// Мягкое предупреждение правки (docs/design/signing-route.md, 12.7): сервер ничего не запрещает,
// фронтенд один раз спрашивает перед первым изменением документа, который держит идущий маршрут.

/** Документ, который держит идущий маршрут, в раунде, на который отвечает автор. */
export type HeldDoc = {
  docId: string;
  routeId: string;
  round: number;
};

/** Что меняет действие: свои документы, файлы по путям или проект целиком (поля, общие файлы). */
export type GuardTarget = {
  docIds?: readonly string[];
  paths?: readonly string[];
  project?: boolean;
};

/** Папка документа: по ней файл относится к документу; общие файлы лежат вне папок документов. */
export type GuardDoc = {
  id: string;
  name: string;
  folder: string;
};

/**
 * Документы идущих маршрутов. Спрашивает только `active`: у остановленного, возвращённого и
 * завершённого вместо вопроса плашка. Сводка без `docs` (сервер до R16) ничего не держит.
 */
export const heldDocsOf = (
  routes: readonly SigningRouteSummary[],
): HeldDoc[] =>
  routes
    .filter((route) => route.status === "active")
    .flatMap((route) =>
      (route.docs ?? []).map((docId) => ({
        docId,
        routeId: route.id,
        round: route.round,
      })),
    );

/** Ключ `sessionStorage` ответа: новый раунд того же маршрута спрашивает снова. */
export const guardKey = (projectId: string, held: HeldDoc): string =>
  `hds.route-guard.${projectId}.${held.docId}.${held.routeId}.${String(held.round)}`;

/** Папка исходника документа: `vkr/vkr.tex` даёт `vkr`, `ivanov/vkr/vkr.tex` даёт `ivanov/vkr`. */
export const folderOf = (sourceFile: string): string => {
  const normalized = sourceFile.replace(/\\/g, "/").replace(/^\.?\//, "");
  const cut = normalized.lastIndexOf("/");
  return cut <= 0 ? "" : normalized.slice(0, cut);
};

const normalizePath = (path: string): string =>
  path.replace(/\\/g, "/").replace(/^\.?\//, "");

/**
 * Документ, в папке которого лежит файл; самая глубокая папка выигрывает. null: файл общий
 * (`common/`, библиография, корень проекта).
 */
export const docOfPath = (
  path: string,
  docs: readonly GuardDoc[],
): string | null => {
  const target = normalizePath(path);
  let best: GuardDoc | null = null;
  for (const doc of docs) {
    if (doc.folder === "") continue;
    if (target !== doc.folder && !target.startsWith(`${doc.folder}/`)) continue;
    if (best === null || doc.folder.length > best.folder.length) best = doc;
  }
  return best?.id ?? null;
};

/**
 * Какие документы на подписании задевает действие. Файл в папке документа задевает только его,
 * общий файл и поля проекта задевают все документы на подписании.
 */
export const affectedHeld = (
  target: GuardTarget,
  held: readonly HeldDoc[],
  docs: readonly GuardDoc[],
): HeldDoc[] => {
  if (held.length === 0) return [];
  let wholeProject = target.project === true;
  const ids = new Set(target.docIds ?? []);
  for (const path of target.paths ?? []) {
    const docId = docOfPath(path, docs);
    if (docId === null) wholeProject = true;
    else ids.add(docId);
  }
  return wholeProject ? [...held] : held.filter((h) => ids.has(h.docId));
};

/**
 * Действие касается одного документа (его файл, его сборка): окно без перечня. Общий файл,
 * поля проекта и «Собрать всё» перечисляют документы.
 */
export const isOwnTarget = (
  target: GuardTarget,
  docs: readonly GuardDoc[],
): boolean => {
  if (target.project === true) return false;
  const ids = new Set(target.docIds ?? []);
  for (const path of target.paths ?? []) {
    const docId = docOfPath(path, docs);
    if (docId === null) return false;
    ids.add(docId);
  }
  return ids.size === 1;
};

/** Память ответов на сеанс: `sessionStorage`, а без доступа к нему до перезагрузки страницы. */
export type GuardMemory = {
  has: (key: string) => boolean;
  add: (key: string) => void;
};

const sessionStore = (): Storage | null => {
  try {
    return window.sessionStorage;
  } catch {
    return null;
  }
};

export const createGuardMemory = (
  storage: () => Storage | null = sessionStore,
): GuardMemory => {
  const local = new Set<string>();
  return {
    has: (key) => {
      if (local.has(key)) return true;
      try {
        return storage()?.getItem(key) === "1";
      } catch {
        return false;
      }
    },
    add: (key) => {
      local.add(key);
      try {
        storage()?.setItem(key, "1");
      } catch {
        // Хранилище недоступно или полно: ответ помнится до перезагрузки страницы.
      }
    },
  };
};

/** Общая память вкладки: окно спрашивает один раз, сколько бы мест ни правило документ. */
export const routeGuardMemory = createGuardMemory();
