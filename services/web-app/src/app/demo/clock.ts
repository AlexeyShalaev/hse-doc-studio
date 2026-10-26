// Время в демо считаем от «сейчас»: данные всегда выглядят свежими, а тесты
// подменяют часы через vi.useFakeTimers.

export const nowMs = (): number => Date.now();

export const isoAt = (ms: number): string => new Date(ms).toISOString();

export const isoAgo = (ms: number): string => isoAt(nowMs() - ms);

export const MINUTE = 60_000;
export const HOUR = 60 * MINUTE;
export const DAY = 24 * HOUR;

let counter = 0;

// Детерминированные «случайные» идентификаторы: стабильны внутри запуска.
export const nextId = (prefix: string): string => {
  counter += 1;
  return `${prefix}-${counter.toString(36)}${nowMs().toString(36).slice(-4)}`;
};

export const fakeUuid = (seed: number): string => {
  const hex = seed.toString(16).padStart(12, "0");
  return `00000000-0000-4000-8000-${hex}`;
};

export const fakeSha = (seed: string): string => {
  let hash = 2166136261;
  for (const char of seed) {
    hash ^= char.charCodeAt(0);
    hash = Math.imul(hash, 16777619) >>> 0;
  }
  const part = hash.toString(16).padStart(8, "0");
  return (part + part + part + part + part).slice(0, 40);
};
