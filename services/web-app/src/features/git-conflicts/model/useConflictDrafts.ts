import { useCallback, useEffect, useRef, useState } from "react";
import {
  useSaveConflictDraft,
  type ConflictSession,
  type FileResolution,
} from "@entities/git-sync";
import {
  carryOverDrafts,
  draftsFromSession,
  sessionKey,
  type DraftMap,
} from "./conflictModel";

// Выбор пользователя по конфликтам. Живёт здесь, а не только на сервере: счётчики
// и подсветка обновляются по щелчку, а сохранение идёт следом с небольшой
// задержкой. Перед завершением и при уходе с экрана всё дописывается.

export const DRAFT_SAVE_DEBOUNCE_MS = 400;

export type DraftSaveState = "idle" | "dirty" | "saving" | "saved" | "error";

export type ResolutionUpdate =
  FileResolution | ((previous: FileResolution | undefined) => FileResolution);

export type ConflictDrafts = {
  drafts: DraftMap;
  /**
   * Записывает решение по файлу и ставит сохранение в очередь. Можно передать
   * функцию от прежнего решения: она видит самое свежее, а не снимок рендера.
   */
  update: (path: string, resolution: ResolutionUpdate) => void;
  /** Заменяет все выборы сразу (после пересборки сеанса). */
  replace: (next: DraftMap) => void;
  saveState: DraftSaveState;
  /** Растёт после каждого успешного сохранения: от него зависит итоговый дифф. */
  savedRevision: number;
  /** Дописывает всё несохранённое; false, если сервер не принял. */
  flush: () => Promise<boolean>;
  /** Бросает несохранённое: сеанс закрыт (отмена слияния), писать некуда. */
  discard: () => void;
};

export const useConflictDrafts = (
  projectId: string,
  session: ConflictSession,
): ConflictDrafts => {
  const { mutateAsync } = useSaveConflictDraft();
  const key = sessionKey(session);

  const [state, setState] = useState(() => ({
    key,
    drafts: draftsFromSession(session),
  }));
  // Сеанс пересобрали: оставляем выборы по файлам, что всё ещё конфликтуют, а
  // чего у нас нет, берём у сервера (например, после правки в другой вкладке).
  // Состояние подстраивается прямо в рендере, как в оболочке рабочей области.
  let drafts = state.drafts;
  if (state.key !== key) {
    drafts = {
      ...draftsFromSession(session),
      ...carryOverDrafts(state.drafts, session),
    };
    setState({ key, drafts });
  }

  const latest = useRef<DraftMap>(drafts);
  useEffect(() => {
    latest.current = drafts;
  }, [drafts]);

  const [saveState, setSaveState] = useState<DraftSaveState>("idle");
  const [savedRevision, setSavedRevision] = useState(0);
  const dirty = useRef(false);
  // Отдельная функция: после присваивания `dirty.current = false` TypeScript
  // считал бы, что значение так и осталось, хотя за время запроса оно менялось.
  const isDirty = (): boolean => dirty.current;
  const timer = useRef<ReturnType<typeof setTimeout> | undefined>(undefined);
  const inflight = useRef<Promise<boolean> | null>(null);
  const closed = useRef(false);

  const persist = useCallback((): Promise<boolean> => {
    clearTimeout(timer.current);
    const previous = inflight.current;
    const run = (async (): Promise<boolean> => {
      if (previous) await previous;
      if (closed.current || !dirty.current) return true;
      dirty.current = false;
      setSaveState("saving");
      try {
        await mutateAsync({ projectId, resolutions: latest.current });
        setSavedRevision((n) => n + 1);
        setSaveState(isDirty() ? "dirty" : "saved");
        return true;
      } catch {
        dirty.current = true;
        setSaveState("error");
        return false;
      }
    })();
    inflight.current = run;
    void run.then(() => {
      if (inflight.current === run) inflight.current = null;
    });
    return run;
  }, [mutateAsync, projectId]);

  const schedule = useCallback((): void => {
    dirty.current = true;
    setSaveState("dirty");
    clearTimeout(timer.current);
    timer.current = setTimeout(() => {
      void persist();
    }, DRAFT_SAVE_DEBOUNCE_MS);
  }, [persist]);

  const update = useCallback(
    (path: string, resolution: ResolutionUpdate): void => {
      const value =
        typeof resolution === "function"
          ? resolution(latest.current[path])
          : resolution;
      const next = { ...latest.current, [path]: value };
      latest.current = next;
      setState((prev) => ({ ...prev, drafts: next }));
      schedule();
    },
    [schedule],
  );

  const replace = useCallback(
    (next: DraftMap): void => {
      latest.current = next;
      setState((prev) => ({ ...prev, drafts: next }));
      schedule();
    },
    [schedule],
  );

  const flush = useCallback(async (): Promise<boolean> => {
    // Пока шло сохранение, могли добавиться новые выборы: идём, пока не пусто.
    for (let attempt = 0; attempt < 5; attempt += 1) {
      if (!dirty.current && !inflight.current) return true;
      if (!(await persist())) return false;
    }
    return !dirty.current;
  }, [persist]);

  const discard = useCallback((): void => {
    closed.current = true;
    dirty.current = false;
    clearTimeout(timer.current);
    setSaveState("idle");
  }, []);

  // Уходим с экрана (или сеанс пересобран): то, что не успели записать, дописываем.
  useEffect(() => {
    closed.current = false;
    return () => {
      clearTimeout(timer.current);
      if (dirty.current && !closed.current) void persist();
    };
  }, [persist]);

  return {
    drafts,
    update,
    replace,
    saveState,
    savedRevision,
    flush,
    discard,
  };
};
