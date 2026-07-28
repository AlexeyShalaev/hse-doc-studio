/**
 * Как часто вообще спрашивать фид релизов.
 *
 * Проверку делает бэкенд, и он же помнит момент последнего удачного ответа
 * (data_dir/update-check.json), поэтому TTL считается от `update_checked_at` из
 * `/system/info`: отметка общая для всех вкладок и переживает перезагрузку — в
 * отличие от прежней записи в localStorage. Релизы выходят раз в недели, так что
 * минуты здесь были бы холостым трафиком; за «прямо сейчас» отвечает кнопка
 * «Проверить обновления» — она идёт мимо TTL.
 */
export const UPDATE_CHECK_TTL_MS = 2 * 60 * 60 * 1000;

/**
 * Пора ли проверять снова. Нет отметки или она нечитаема → да: лучше один лишний
 * запрос, чем молча никогда не узнать о новой версии.
 */
export const isCheckStale = (
  checkedAt: string | null | undefined,
  now: number = Date.now(),
): boolean => {
  if (!checkedAt) return true;
  const at = Date.parse(checkedAt);
  if (Number.isNaN(at)) return true;
  return now - at >= UPDATE_CHECK_TTL_MS;
};
