import type { CatalogSource } from "@entities/pack-catalog";

/**
 * Одно слово о состоянии источника вместо четырёх строк: что с ним происходит
 * и нужно ли что-то делать. Порядок важен: идущая проверка и ошибка важнее
 * выключенности, «нужно проверить» важнее «есть новые версии».
 */
export type SourceStatus =
  /** Идёт проверка или применение. */
  | "busy"
  /** Последняя проверка не удалась. */
  | "failed"
  /** Источник выключен: его паки скрыты из мастера. */
  | "off"
  /** Ещё ни разу не подключался. */
  | "new"
  /** Проверка нашла препятствия: применить нельзя. */
  | "blocked"
  /** Проверка нашла новые версии, их можно применить. */
  | "update"
  /** Всё подключено, нового нет. */
  | "ok";

export const sourceStatus = (source: CatalogSource): SourceStatus => {
  if (source.busy) return "busy";
  if (source.error) return "failed";
  if (!source.enabled) return "off";
  if (source.applied_revision === null) return "new";
  if (source.checked_at !== null && source.check_ok === false) return "blocked";
  if (source.pending_versions > 0) return "update";
  return "ok";
};

/** Состояние требует действия: тогда «Проверить» главная кнопка карточки, иначе обычная. */
export const needsAttention = (status: SourceStatus): boolean =>
  status === "failed" ||
  status === "new" ||
  status === "blocked" ||
  status === "update";
