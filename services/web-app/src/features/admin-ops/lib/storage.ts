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

// Доля занятого диска, с которой полоса желтеет; красной её делает isLowSpace.
const WARN_USED = 80;

/**
 * Тон диска проектов: «danger», когда места мало, «warning» с 80% занятого.
 * Один и тот же на странице «Хранилище», в сводке и в навигации.
 */
export const diskTone = (
  storage: AdminStorage,
): "danger" | "warning" | "neutral" => {
  if (isLowSpace(storage)) return "danger";
  const total = storage.volume_total_bytes;
  const free = storage.free_bytes;
  if (total === null || free === null || total <= 0) return "neutral";
  return ((total - free) / total) * 100 >= WARN_USED ? "warning" : "neutral";
};
