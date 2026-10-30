/** Что экрану известно о человеке из справочника пользователей. */
export type OpsPerson = { name: string; email: string };

/** Человек для PersonCell: имя из справочника, иначе из ответа; id только для цвета и подсказки. */
export type PersonRef = {
  id: string;
  name: string | null;
  email: string | null;
};

const clean = (value: string | null | undefined): string | null => {
  const text = value?.trim() ?? "";
  return text === "" ? null : text;
};

export const personRef = (
  id: string,
  known: string | null | undefined,
  people: ReadonlyMap<string, OpsPerson>,
): PersonRef => {
  const found = people.get(id);
  const name = clean(found?.name) ?? clean(known);
  return { id, name, email: found?.email ?? null };
};

/** Короткая ссылка на объект без имени: хвост идентификатора, по нему его можно найти в логах. */
export const shortRef = (id: string): string => {
  const tail = id.replace(/[^0-9a-z]/gi, "");
  return tail.slice(-6).toLowerCase();
};
