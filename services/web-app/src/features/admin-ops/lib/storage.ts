import type { AdminStorage } from "@entities/session";

/** Свободного места меньше этого запаса (или доли диска) считается опасным. */
const LOW_FREE_BYTES = 5 * 1024 ** 3;
const LOW_FREE_SHARE = 0.1;

export const isLowSpace = (storage: AdminStorage): boolean => {
  if (storage.free_bytes === null) return false;
  const disk = storage.volume_total_bytes ?? 0;
  return (
    storage.free_bytes < LOW_FREE_BYTES ||
    (disk > 0 && storage.free_bytes / disk < LOW_FREE_SHARE)
  );
};
