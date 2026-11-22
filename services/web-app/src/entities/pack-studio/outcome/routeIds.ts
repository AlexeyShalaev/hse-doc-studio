// Идентификаторы элементов точек и маршрута в адресе (`selected=points:<id>`, `selected=route:<id>`).
// Те же строки строит сервер (core/pack_studio/outcome/points.py: `step_id`, `pair_id`), по ним
// правая панель и «Что изменилось» находят элемент, поэтому формат менять нельзя.

/** Точка целиком: `points:<точка>`. */
export const pointId = (point: string): string => point;

/** Пункт точки: `points:<точка>/<документ>`. */
export const itemId = (point: string, doc: string): string => `${point}/${doc}`;

/** Файл `extra_items`: `points:<точка>/<источник>`. */
export const extraId = (point: string, source: string): string =>
  `${point}/${source}`;

/** Шаг маршрута: `route:<точка>/step/<номер с 1>`. */
export const stepId = (point: string, number: number): string =>
  `${point}/step/${String(number)}`;

/** Пара документ и слот; у персоны не по слоту (автор команды) в конце персона. */
export const pairId = (
  point: string,
  doc: string,
  slot: string,
  persona: string,
): string => {
  const base = `${point}/${doc}/${slot}`;
  return persona === slot ? base : `${base}/${persona}`;
};
