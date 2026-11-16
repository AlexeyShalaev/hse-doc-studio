// Запись манифеста по JSON Pointer (RFC 6901): указатель приходит от сервера вместе с правилом
// (R14), здесь он только разбирается и читается в данных модели версии. Условий пака тут нет.

/** Путь точечной правки YAML: ключи словарей и индексы списков. */
export type YamlPath = (string | number)[];

export type Resolved = {
  /** Путь для правки; индексы списков числами. */
  path: YamlPath;
  /** Значение записи (`undefined`, если ключа нет). */
  value: unknown;
  /** Запись есть в манифесте. */
  exists: boolean;
  /** Родитель записи это список (запись удаляется вставкой обратно по индексу). */
  inList: boolean;
};

const unescape = (segment: string): string =>
  segment.replace(/~1/g, "/").replace(/~0/g, "~");

export const decodePointer = (pointer: string): string[] =>
  pointer === "" ? [] : pointer.slice(1).split("/").map(unescape);

const isRecord = (value: unknown): value is Record<string, unknown> =>
  typeof value === "object" && value !== null && !Array.isArray(value);

/**
 * Найти запись в данных манифеста. `null`, если по пути нет даже родителя: правка не имеет
 * смысла (манифест изменили мимо экрана), и экран предложит обновить результат.
 */
export const resolvePointer = (
  root: unknown,
  pointer: string,
): Resolved | null => {
  const segments = decodePointer(pointer);
  if (segments.length === 0) return null;
  const path: YamlPath = [];
  let current: unknown = root;
  for (let i = 0; i < segments.length; i += 1) {
    const segment = segments[i] ?? "";
    const last = i === segments.length - 1;
    if (Array.isArray(current)) {
      const index = Number(segment);
      if (!Number.isInteger(index) || index < 0) return null;
      path.push(index);
      if (last) {
        const exists = index < current.length;
        return { path, value: current[index], exists, inList: true };
      }
      current = current[index];
    } else if (isRecord(current)) {
      path.push(segment);
      if (last) {
        const exists = Object.prototype.hasOwnProperty.call(current, segment);
        return { path, value: current[segment], exists, inList: false };
      }
      current = current[segment];
    } else {
      return null;
    }
  }
  return null;
};

/** Равенство данных манифеста (то, что приходит из JSON): значения, списки, словари. */
export const sameData = (a: unknown, b: unknown): boolean => {
  if (a === b) return true;
  if (Array.isArray(a) && Array.isArray(b)) {
    return a.length === b.length && a.every((item, i) => sameData(item, b[i]));
  }
  if (isRecord(a) && isRecord(b)) {
    const keys = Object.keys(a);
    return (
      keys.length === Object.keys(b).length &&
      keys.every(
        (key) =>
          Object.prototype.hasOwnProperty.call(b, key) &&
          sameData(a[key], b[key]),
      )
    );
  }
  return false;
};
