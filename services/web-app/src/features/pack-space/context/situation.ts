// Условия студента в адресе: `i.<условие>=<значение>` и `case=<готовый случай>`. Формат тот же,
// что у прежнего экрана «Результат» (features/pack-outcome/lib/urlState.ts), поэтому ссылка со
// старого экрана открывается в новом с теми же условиями. Пределы как у сервера: до 64 условий,
// значение до 128 знаков. Невалидное отбрасывается: чужой адрес даёт умолчания, а не ошибку.

import { SPACE_QUERY } from "@entities/pack-studio";

export const MAX_INPUTS = 64;
export const MAX_INPUT_VALUE = 128;

const KEY = /^[a-z][a-z0-9_.-]{0,63}$/;
const CASE = /^[A-Za-z0-9][A-Za-z0-9._-]{0,127}$/;
const CONTROL = /\p{Cc}/u;

export type Situation = {
  inputs: Record<string, string>;
  /** Готовый случай, чьи условия взяты за основу; `null`: свои условия. */
  caseId: string | null;
};

/** Оставляет только валидные пары, не больше `MAX_INPUTS`. */
export const cleanInputs = (
  raw: Iterable<readonly [string, string]>,
): Record<string, string> => {
  const out: Record<string, string> = {};
  let count = 0;
  for (const [key, value] of raw) {
    if (count >= MAX_INPUTS) break;
    if (!KEY.test(key) || key in out) continue;
    if (value.length === 0 || value.length > MAX_INPUT_VALUE) continue;
    if (CONTROL.test(value)) continue;
    out[key] = value;
    count += 1;
  }
  return out;
};

export const isCaseId = (value: string | null): value is string =>
  value !== null && CASE.test(value);

/** Условия и случай из query. */
export const readSituation = (search: string): Situation => {
  const params = new URLSearchParams(search);
  const pairs: [string, string][] = [];
  params.forEach((value, name) => {
    if (name.startsWith(SPACE_QUERY.inputPrefix)) {
      pairs.push([name.slice(SPACE_QUERY.inputPrefix.length), value]);
    }
  });
  const id = params.get(SPACE_QUERY.case);
  return { inputs: cleanInputs(pairs), caseId: isCaseId(id) ? id : null };
};

/** Записать условия в `params` (прежние `i.*` заменяются целиком, порядок по имени). */
export const writeInputs = (
  params: URLSearchParams,
  inputs: Record<string, string>,
): void => {
  for (const name of [...params.keys()]) {
    if (name.startsWith(SPACE_QUERY.inputPrefix)) params.delete(name);
  }
  Object.entries(cleanInputs(Object.entries(inputs)))
    .sort(([a], [b]) => (a < b ? -1 : a > b ? 1 : 0))
    .forEach(([key, value]) => {
      params.set(`${SPACE_QUERY.inputPrefix}${key}`, value);
    });
};
