import { flushPendingSaves, hasUnsavedChanges } from "../pendingSaves";
import { isChunkLoadError } from "./chunkError";
import { useStaleBuildStore, type StaleReason } from "./staleBuildStore";

/** Метка последней автоматической перезагрузки: по ней вкладка не уходит в цикл. */
export const RELOAD_STAMP_KEY = "hds:stale-build-reload-at";
/** Если ошибка повторилась раньше, чем через это время после перезагрузки, снова не перезагружаем. */
export const RELOAD_GUARD_MS = 60_000;

export type StaleOutcome = "reloading" | "notice";

const readStamp = (): number | null => {
  try {
    const raw = window.sessionStorage.getItem(RELOAD_STAMP_KEY);
    const value = raw === null ? Number.NaN : Number(raw);
    return Number.isFinite(value) ? value : null;
  } catch {
    return null;
  }
};

/** Без доступного sessionStorage защититься от цикла нечем, поэтому автоперезагрузка запрещена. */
const writeStamp = (now: number): boolean => {
  try {
    window.sessionStorage.setItem(RELOAD_STAMP_KEY, String(now));
    return true;
  } catch {
    return false;
  }
};

const canAutoReload = (now: number): boolean => {
  const stamp = readStamp();
  return stamp === null || now - stamp > RELOAD_GUARD_MS || stamp > now;
};

/**
 * Вкладка собрана из файлов, которых на сервере уже нет. Один раз перезагружаем её сами, если нет
 * несохранённого ввода и в этой вкладке недавно не перезагружали; иначе остаётся сообщение с кнопкой.
 */
export const handleStaleBuild = (
  reason: StaleReason,
  now: number = Date.now(),
): StaleOutcome => {
  useStaleBuildStore.getState().markStale(reason);
  if (reason !== "chunk") return "notice";
  if (hasUnsavedChanges() || !canAutoReload(now) || !writeStamp(now)) {
    return "notice";
  }
  window.location.reload();
  return "reloading";
};

/** Кнопка «Обновить»: сперва просим редакторы записать правки, потом перезагружаем. */
export const reloadToNewBuild = async (): Promise<void> => {
  try {
    await flushPendingSaves();
  } finally {
    window.location.reload();
  }
};

export const reportIfChunkError = (error: unknown): boolean => {
  if (!isChunkLoadError(error)) return false;
  handleStaleBuild("chunk");
  return true;
};

/**
 * `vite:preloadError` и необработанные отказы промисов с ошибкой загрузки модуля. Событие Vite не
 * отменяем: ошибка идёт дальше в границу маршрута, которая покажет то же сообщение.
 */
export const installStaleBuildGuard = (): (() => void) => {
  const onPreload = (event: Event): void => {
    const { payload } = event as Event & { payload?: unknown };
    reportIfChunkError(payload);
  };
  const onRejection = (event: PromiseRejectionEvent): void => {
    reportIfChunkError(event.reason);
  };
  window.addEventListener("vite:preloadError", onPreload);
  window.addEventListener("unhandledrejection", onRejection);
  return () => {
    window.removeEventListener("vite:preloadError", onPreload);
    window.removeEventListener("unhandledrejection", onRejection);
  };
};
