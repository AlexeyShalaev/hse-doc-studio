import { create } from "zustand";
import { createSSEStream } from "@shared/lib/sse";
import { env } from "@shared/config";

export type CompileStatus = "running" | "success" | "failure" | "cancelled";

export type CompileDoneInfo = {
  status: "success" | "failure" | "cancelled";
  pages: number | null;
  warnings: number;
  errors: number;
};

export type CompileStreamSlot = {
  compileId: string;
  logLines: string[];
  status: CompileStatus;
  doneInfo: CompileDoneInfo | null;
  /** Wall-clock of the last log line, used by the idle watchdog. */
  lastEventAt: number;
  /** Watchdog flag: no log lines for STALE_THRESHOLD_MS while status=running. */
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

const streamUrl = (projectId: string, compileId: string): string =>
  `${env.VITE_API_BASE_URL}/api/v1/projects/${projectId}/compiles/${compileId}/stream`;

// 90s with no output is past the docker pull / font cache phase, so it
// almost certainly means the build is wedged. The backend has its own
// idle_timeout (default 120s) that will kill+save failure; this just lets
// the user act sooner.
const STALE_THRESHOLD_MS = 90_000;
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
              const data = event.data as CompileDoneInfo;
              const closer = s._closers[k];
              if (closer) closer();
              const nextClosers = omitKey(s._closers, k);
              return {
                streams: {
                  ...s.streams,
                  [k]: {
                    ...slot,
                    doneInfo: data,
                    status: data.status,
                    isStalled: false,
                    lastEventAt: Date.now(),
                  },
                },
                _closers: nextClosers,
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
            [k]: { ...slot, status: "cancelled", isStalled: false },
          },
          _closers: nextClosers,
          pending: nextPending,
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
        const shouldBeStalled = now - slot.lastEventAt > STALE_THRESHOLD_MS;
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
