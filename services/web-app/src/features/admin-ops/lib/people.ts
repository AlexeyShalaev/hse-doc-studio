/** Человек для PersonCell: имя и почта из строки ответа; id только для цвета и подсказки. */
export type PersonRef = {
  id: string;
  name: string | null;
  email: string | null;
};

const clean = (value: string | null | undefined): string | null => {
  const text = value?.trim() ?? "";
  return text === "" ? null : text;
};

/**
 * Имя и почту сервер кладёт в саму строку (JOIN). Пустое имя значит, что
 * человека уже нет: экран пишет нейтральную подпись, а не идентификатор.
 */
export const personRef = (
  id: string,
  name: string | null | undefined,
  email: string | null | undefined,
): PersonRef => ({ id, name: clean(name), email: clean(email) });

/** Короткая ссылка на объект без имени: хвост идентификатора, по нему его можно найти в логах. */
export const shortRef = (id: string): string => {
  const tail = id.replace(/[^0-9a-z]/gi, "");
  return tail.slice(-6).toLowerCase();
};
