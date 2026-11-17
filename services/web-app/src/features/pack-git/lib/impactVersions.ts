import {
  versionRefOf,
  type PackFileChange,
  type PackVersionRef,
} from "@entities/pack-studio";

/** Сколько версий с правками считается «до и после» одновременно: расчёт идёт секунды. */
export const MAX_IMPACT_VERSIONS = 3;

const keyOf = (v: PackVersionRef): string =>
  `${v.pack}/${v.template}/${v.version}`;

/**
 * Версии, в которых что-то изменено (добавлено или правлено): для них считается «до и после».
 * Версия, из которой только удалили файлы, и файлы вне версий (манифесты пака, шаблона) не
 * считаются. Первой идёт версия открытого экрана «Результат», затем по алфавиту; сверх предела
 * версии не считаются, их число в `extra`.
 */
export const impactVersions = (
  changes: readonly PackFileChange[],
  preferred: PackVersionRef | null = null,
): { versions: PackVersionRef[]; extra: number } => {
  const found = new Map<string, PackVersionRef>();
  for (const change of changes) {
    if (change.status === "deleted") continue;
    const ref = versionRefOf(change.path);
    if (ref) found.set(keyOf(ref), ref);
  }
  const first = preferred ? keyOf(preferred) : null;
  const all = [...found.values()].sort((a, b) => {
    if (keyOf(a) === first) return -1;
    if (keyOf(b) === first) return 1;
    return keyOf(a) < keyOf(b) ? -1 : keyOf(a) > keyOf(b) ? 1 : 0;
  });
  return {
    versions: all.slice(0, MAX_IMPACT_VERSIONS),
    extra: Math.max(0, all.length - MAX_IMPACT_VERSIONS),
  };
};
