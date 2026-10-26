// Registry of "write my unsaved edits now" callbacks. Editors and the project
// settings panel autosave after a pause; an operation that reads the project
// from disk (a git sync, a snapshot, a move) calls `flushPendingSaves()` first
// so those edits are part of it instead of racing it.

export type PendingSaveFlush = () => void | Promise<void>;

export type FlushResult = {
  /** Callbacks that ran. */
  total: number;
  /** Callbacks that threw or rejected; the caller decides whether to go on. */
  failed: number;
};

const registry = new Set<PendingSaveFlush>();

/** Register a callback; returns the function that removes it. */
export const registerPendingSave = (flush: PendingSaveFlush): (() => void) => {
  registry.add(flush);
  return () => {
    registry.delete(flush);
  };
};

/** Run every registered callback and wait until all of them settled. */
export const flushPendingSaves = async (): Promise<FlushResult> => {
  const callbacks = [...registry];
  const results = await Promise.allSettled(
    callbacks.map(async (flush) => {
      await flush();
    }),
  );
  return {
    total: callbacks.length,
    failed: results.filter((r) => r.status === "rejected").length,
  };
};
