import { create } from "zustand";
import { createSSEStream } from "@shared/lib/sse";
import { env } from "@shared/config";
import { CompileWaitSchema, type CompileWait } from "@entities/session";
import { CompileErrorSchema, type CompileError } from "@entities/document";
import { parsePlacement, type CompilePlacement } from "@entities/runner";
import { isSlotStalled, parsePhase } from "./compilePhase";

export type CompileStatus = "running" | "success" | "failure" | "cancelled";

export type CompileDoneInfo = {
  status: "success" | "failure" | "cancelled";
  pages: number | null;
  warnings: number;
  errors: number;
  /** Серверный режим: почему сборка не дошла до конца (заменена, нет раннера). */
  wait?: CompileWait | null;
  /** Причина неудачной или отменённой сборки: код, деталь и текст «что делать». */
  error?: CompileError | null;
  /**
   * Сколько мест подписей из шаблона встали по строкам шаблона этой сборки (signing-route.md,
   * 15.17.9); 0 или нет поля у сервера без якорей.
   */
  signature_places_moved?: number;
};

export type CompileStreamSlot = {
  compileId: string;
  logLines: string[];
  status: CompileStatus;
  doneInfo: CompileDoneInfo | null;
  /**
   * Серверный режим: сборка ждёт очереди или раннера (событие потока `wait`).
   * null, пока сборка идёт или в локальном режиме.
   */
  wait: CompileWait | null;
  /**
   * Серверный режим: где идёт сборка (событие потока `placement`): ждёт личный
   * раннер, на личном, на общем или на общем после фолбэка. null в локальном.
   */
  placement: CompilePlacement | null;
  /**
   * Серверный режим: задача ждёт раннера («queued») или раннер её уже взял («running»), по событию потока
   * `phase`. null: события ещё не было (или локальный режим, где сборка идёт сразу).
   */
  phase: "queued" | "running" | null;
  /** Когда эта вкладка увидела, что раннер взял сборку (или время запуска с сервера при подключении позже). */
  runStartedAt: number | null;
  /** Загрузка подходящих раннеров, пока сборка в очереди. */
  load: { busy: number; capacity: number } | null;
  /** Wall-clock of the last event or log line of THIS build, used by the idle watchdog. */
  lastEventAt: number;
  /**
   * Watchdog flag: запущенная раннером сборка молчит дольше порога. Очередь и ожидание раннера не считаются:
   * отсчёт идёт не от нажатия «Собрать», а от запуска и последней строки вывода.
   */
  isStalled: boolean;
};

type StoreState = {
  streams: Record<string, CompileStreamSlot>;
  pending: Record<string, true>;
  _closers: Record<string, () => void>;
};

type StoreActions = {
  markPending: (projectId: string, docId: string) => void;
  unmarkPending: (projectId: string, docId: string) => void;
  start: (projectId: string, docId: string, compileId: string) => void;
  /** Clear a slot. Closes SSE if alive. Use after server-side cancel. */
  clear: (projectId: string, docId: string) => void;
  /**
   * Mark a slot's status as cancelled locally without waiting for SSE.
   * Called right after a successful POST /cancel so the UI flips immediately.
   */
  markCancelled: (projectId: string, docId: string) => void;
  /**
   * Закрыть слот «идёт» по данным сервера: документ уже не `building`, а слот ещё ждёт `done`
   * (поток оборвался без события). Без этого упавшая сборка висела бы «зависшей» с кнопкой «Остановить».
   * Слот другой сборки (другой compileId) не трогаем.
   */
  settleFromServer: (
    projectId: string,
    docId: string,
    compileId: string,
    status: "success" | "failure",
  ) => void;
  /** Re-evaluate isStalled across all running slots. Called by the watchdog. */
  tickWatchdog: () => void;
};

const key = (projectId: string, docId: string) => `${projectId}::${docId}`;

/**
 * Shallow copy of `source` without the `dropKey` entry. Rest-destructuring
 * instead of `delete` keeps the records dense (no deleted-key deopt) and the
 * slot maps immutable, which is what zustand consumers expect.
 */
const omitKey = <T>(
  source: Record<string, T>,
  dropKey: string,
): Record<string, T> => {
  const { [dropKey]: _dropped, ...rest } = source;
  return rest;
};

/** Событие `done`: причину сбоя разбираем схемой, чтобы кривое тело не сломало плашку. */
const parseDone = (raw: unknown): CompileDoneInfo => {
  const data = raw as CompileDoneInfo;
  const parsed = CompileErrorSchema.nullish().safeParse(data.error);
  const moved = data.signature_places_moved;
  return {
    ...data,
    error: parsed.success ? (parsed.data ?? null) : null,
    signature_places_moved:
      typeof moved === "number" && Number.isInteger(moved) && moved > 0
        ? moved
        : 0,
  };
};

const streamUrl = (projectId: string, compileId: string): string =>
  `${env.VITE_API_BASE_URL}/api/v1/projects/${projectId}/compiles/${compileId}/stream`;

// Пороги тишины живут в compilePhase.ts: 5 минут для запущенной раннером сборки (как простой раннера, 300 с)
// и 90 секунд без событий `phase` (локальный режим: бэкенд сам снимает сборку через 120 с простоя).
const WATCHDOG_INTERVAL_MS = 5_000;

export const useCompileStreamStore = create<StoreState & StoreActions>(
  (set, get) => ({
    streams: {},
    pending: {},
    _closers: {},

    markPending: (projectId, docId) => {
      const k = key(projectId, docId);
      set((s) => ({ pending: { ...s.pending, [k]: true } }));
    },

    unmarkPending: (projectId, docId) => {
      const k = key(projectId, docId);
      set((s) => {
        if (!s.pending[k]) return s;
        return { pending: omitKey(s.pending, k) };
      });
    },

    start: (projectId, docId, compileId) => {
      const k = key(projectId, docId);

      const prevClose = get()._closers[k];
      if (prevClose) prevClose();

      set((s) => {
        const nextPending = omitKey(s.pending, k);
        return {
          streams: {
            ...s.streams,
            [k]: {
              compileId,
              logLines: [],
              status: "running",
              doneInfo: null,
              wait: null,
              placement: null,
              phase: null,
              runStartedAt: null,
              load: null,
              lastEventAt: Date.now(),
              isStalled: false,
            },
          },
          pending: nextPending,
        };
      });

      const close = createSSEStream<unknown>(
        streamUrl(projectId, compileId),
        (event) => {
          set((s) => {
            const slot = s.streams[k];
            if (slot?.compileId !== compileId) return s;

            if (event.type === "done") {
              const data = parseDone(event.data);
              const closer = s._closers[k];
              if (closer) closer();
              const nextClosers = omitKey(s._closers, k);
              return {
                streams: {
                  ...s.streams,
                  [k]: {
                    ...slot,
                    doneInfo: data,
                    wait: data.wait ?? null,
                    status: data.status,
                    isStalled: false,
                    lastEventAt: Date.now(),
                  },
                },
                _closers: nextClosers,
              };
            }

            if (event.type === "placement") {
              // Место сборки не значит вывод: сторож тишины не сбрасывается.
              return {
                streams: {
                  ...s.streams,
                  [k]: { ...slot, placement: parsePlacement(event.data) },
                },
              };
            }

            if (event.type === "phase") {
              const phase = parsePhase(event.data);
              if (phase === null) return s;
              const now = Date.now();
              const started =
                slot.phase !== "running" && phase.phase === "running";
              const startedAtServer =
                phase.started_at === null
                  ? Number.NaN
                  : Date.parse(phase.started_at);
              return {
                streams: {
                  ...s.streams,
                  [k]: {
                    ...slot,
                    phase: phase.phase,
                    // Раннер взял задачу: молчание считается с этого момента, а не с нажатия кнопки.
                    runStartedAt: started
                      ? slot.phase === null && !Number.isNaN(startedAtServer)
                        ? Math.min(now, startedAtServer)
                        : now
                      : slot.runStartedAt,
                    load:
                      phase.phase === "queued" &&
                      phase.runners_capacity != null &&
                      phase.runners_busy != null
                        ? {
                            busy: phase.runners_busy,
                            capacity: phase.runners_capacity,
                          }
                        : null,
                    lastEventAt: started ? now : slot.lastEventAt,
                    isStalled: started ? false : slot.isStalled,
                  },
                },
              };
            }

            if (event.type === "wait") {
              const parsed = CompileWaitSchema.safeParse(event.data);
              // Пустое или непонятное тело снимает ожидание: сборка пошла.
              return {
                streams: {
                  ...s.streams,
                  [k]: {
                    ...slot,
                    wait: parsed.success ? parsed.data : null,
                    lastEventAt: Date.now(),
                    isStalled: false,
                  },
                },
              };
            }

            const data = event.data;
            let line: string | null = null;
            if (typeof data === "string") line = data;
            else if (data && typeof data === "object") {
              const m = (data as { line?: unknown }).line;
              if (typeof m === "string") line = m;
            }
            if (line === null) return s;

            return {
              streams: {
                ...s.streams,
                [k]: {
                  ...slot,
                  logLines: [...slot.logLines, line],
                  // Пошёл вывод раннера: сборка уже идёт, ожидание снято.
                  wait: null,
                  phase: slot.phase === "queued" ? "running" : slot.phase,
                  runStartedAt:
                    slot.phase === "queued" ? Date.now() : slot.runStartedAt,
                  load: null,
                  lastEventAt: Date.now(),
                  isStalled: false,
                },
              },
            };
          });
        },
        () => {
          set((s) => {
            const slot = s.streams[k];
            if (slot?.status !== "running") return s;
            const nextClosers = omitKey(s._closers, k);
            return {
              streams: {
                ...s.streams,
                [k]: { ...slot, status: "failure", isStalled: false },
              },
              _closers: nextClosers,
            };
          });
        },
      );

      set((s) => ({ _closers: { ...s._closers, [k]: close } }));
    },

    clear: (projectId, docId) => {
      const k = key(projectId, docId);
      const closer = get()._closers[k];
      if (closer) closer();
      set((s) => {
        const nextStreams = omitKey(s.streams, k);
        const nextClosers = omitKey(s._closers, k);
        const nextPending = omitKey(s.pending, k);
        return {
          streams: nextStreams,
          _closers: nextClosers,
          pending: nextPending,
        };
      });
    },

    markCancelled: (projectId, docId) => {
      const k = key(projectId, docId);
      const closer = get()._closers[k];
      if (closer) closer();
      set((s) => {
        const slot = s.streams[k];
        const nextClosers = omitKey(s._closers, k);
        const nextPending = omitKey(s.pending, k);
        if (!slot) {
          return { _closers: nextClosers, pending: nextPending };
        }
        return {
          streams: {
            ...s.streams,
            [k]: { ...slot, status: "cancelled", wait: null, isStalled: false },
          },
          _closers: nextClosers,
          pending: nextPending,
        };
      });
    },

    settleFromServer: (projectId, docId, compileId, status) => {
      const k = key(projectId, docId);
      const slot = get().streams[k];
      if (slot?.status !== "running" || slot.compileId !== compileId) return;
      const closer = get()._closers[k];
      if (closer) closer();
      set((s) => {
        const current = s.streams[k];
        if (current?.status !== "running" || current.compileId !== compileId) {
          return s;
        }
        return {
          streams: {
            ...s.streams,
            [k]: { ...current, status, wait: null, isStalled: false },
          },
          _closers: omitKey(s._closers, k),
        };
      });
    },

    tickWatchdog: () => {
      const now = Date.now();
      const state = get();
      let changed = false;
      const nextStreams = { ...state.streams };
      for (const [k, slot] of Object.entries(state.streams)) {
        if (slot.status !== "running") continue;
        // Очередь и ожидание раннера молчат по делу; тревога только для запущенной сборки.
        const shouldBeStalled = isSlotStalled(slot, now);
        if (shouldBeStalled !== slot.isStalled) {
          nextStreams[k] = { ...slot, isStalled: shouldBeStalled };
          changed = true;
        }
      }
      if (changed) set({ streams: nextStreams });
    },
  }),
);

// Module-level watchdog. Cheap: O(streams) every 5s; effectively a no-op
// when nothing is running. Starts on first import so any consumer of the
// store gets stall detection for free.
if (typeof window !== "undefined") {
  setInterval(() => {
    useCompileStreamStore.getState().tickWatchdog();
  }, WATCHDOG_INTERVAL_MS);
}

export const useCompileSlot = (
  projectId: string,
  docId: string,
): CompileStreamSlot | undefined =>
  useCompileStreamStore((s) => s.streams[key(projectId, docId)]);
