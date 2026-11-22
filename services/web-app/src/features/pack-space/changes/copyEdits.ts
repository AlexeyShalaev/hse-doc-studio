import {
  versionDirOf,
  versionRefOf,
  type PackFileChange,
  type PackVersionRef,
} from "@entities/pack-studio";

// «Что человек изменил» в только что созданной копии версии (pack-studio-ux.md, 4.4, 5.6).
//
// Для git копия это каталог, которого в основной ветке нет: все его файлы «новые», хотя человек
// пока не тронул почти ни одного. Поэтому для открытой версии, чей каталог целиком новый, мы
// сверяем каждый файл с тем же файлом версии, с которой она сделана (`base` из отчёта версии), и
// считаем изменением только то, что отличается. Файлы, совпавшие с основой, из списка и счётчика
// уходят (`same`). Сам файл версии (`version.yaml`) сверяется по данным манифеста без полей,
// которые Студия пишет сама (номер, статус, заметки). Файл вне каталога версии и файл копии без
// пары в основе всегда «мои». Чистые функции без запросов: запросы делает `useCopyScan`.

/** Имя манифеста версии. */
export const VERSION_FILE = "version.yaml";

/** Больше файлов не сверяем (запросов было бы слишком много): считаем как раньше, по git. */
export const MAX_SCAN_FILES = 300;

/** Сколько файлов читаем одновременно. */
export const SCAN_CONCURRENCY = 6;

/**
 * Поля манифеста версии, которые меняют не правки человека, а Студия при копировании, выпуске и
 * записи заметок: на «моё» они не влияют.
 */
export const STUDIO_KEYS: readonly string[] = [
  "id",
  "released_at",
  "status",
  "release",
  "changes",
  "breaking_changes",
];

const sameVersion = (a: PackVersionRef, b: PackVersionRef): boolean =>
  a.pack === b.pack && a.template === b.template && a.version === b.version;

/**
 * Каталог открытой версии, если он целиком новый (копия): в изменениях есть его новый
 * `version.yaml`. Иначе `null`, и версия считается по git как есть.
 */
export const freshCopyDir = (
  changed: readonly PackFileChange[],
  open: PackVersionRef,
): string | null => {
  for (const change of changed) {
    if (change.status !== "added") continue;
    const dir = versionDirOf(change.path);
    const ref = versionRefOf(change.path);
    if (
      dir !== null &&
      ref !== null &&
      sameVersion(ref, open) &&
      change.path === `${dir}/${VERSION_FILE}`
    ) {
      return dir;
    }
  }
  return null;
};

/** Каталог версии `base` рядом с каталогом `dir` (тот же шаблон). */
export const baseDirOf = (dir: string, base: string): string =>
  `${dir.split("/").slice(0, -1).join("/")}/${base}`;

/** Файлы копии, которые нужно сверять с основой: новые файлы каталога, кроме манифеста версии. */
export const scanCandidates = (
  changed: readonly PackFileChange[],
  dir: string,
): string[] =>
  changed
    .filter(
      (change) =>
        change.status === "added" &&
        change.path.startsWith(`${dir}/`) &&
        change.path !== `${dir}/${VERSION_FILE}`,
    )
    .map((change) => change.path);

const stable = (value: unknown): string => {
  if (Array.isArray(value)) return `[${value.map(stable).join(",")}]`;
  if (value !== null && typeof value === "object") {
    const entries = Object.entries(value as Record<string, unknown>)
      .sort(([a], [b]) => a.localeCompare(b))
      .map(([key, item]) => `${JSON.stringify(key)}:${stable(item)}`);
    return `{${entries.join(",")}}`;
  }
  return JSON.stringify(value) ?? "null";
};

/** Манифесты версий совпадают, если не считать поля, которые пишет сама Студия. */
export const sameManifest = (a: unknown, b: unknown): boolean => {
  const strip = (value: unknown): unknown => {
    if (value === null || typeof value !== "object" || Array.isArray(value)) {
      return value;
    }
    return Object.fromEntries(
      Object.entries(value as Record<string, unknown>).filter(
        ([key]) => !STUDIO_KEYS.includes(key),
      ),
    );
  };
  return stable(strip(a)) === stable(strip(b));
};

export type CopyReaders = {
  /** Отпечаток содержимого файла копии; `null`: файла нет или не прочитался. */
  draft: (path: string) => Promise<string | null>;
  /** То же для файла основы. */
  base: (path: string) => Promise<string | null>;
  /** Манифест версии совпадает с манифестом основы (без полей Студии). */
  manifest: () => Promise<boolean>;
};

/**
 * Какие файлы копии совпадают с основой: `version.yaml` (по данным манифеста) и файлы из
 * `candidates` с тем же отпечатком. Файл, который не прочитался с любой стороны, не совпал:
 * лучше показать лишнюю правку, чем потерять настоящую. Читает по `SCAN_CONCURRENCY` штук.
 */
export const findSameFiles = async (
  dir: string,
  baseDir: string,
  candidates: readonly string[],
  read: CopyReaders,
): Promise<Set<string>> => {
  const same = new Set<string>();
  const queue = [...candidates];
  const check = async (path: string) => {
    const [mine, base] = await Promise.all([
      read.draft(path),
      read.base(`${baseDir}${path.slice(dir.length)}`),
    ]);
    if (mine !== null && mine === base) same.add(path);
  };
  const worker = async () => {
    for (let path = queue.shift(); path !== undefined; path = queue.shift()) {
      await check(path);
    }
  };
  const manifest = read
    .manifest()
    .then((equal) => {
      if (equal) same.add(`${dir}/${VERSION_FILE}`);
    })
    .catch(() => undefined);
  await Promise.all([
    manifest,
    ...Array.from({ length: Math.min(SCAN_CONCURRENCY, queue.length) }, worker),
  ]);
  return same;
};

/**
 * Что считать изменённым: список git без файлов, совпавших с основой. `same`: `null` значит
 * «сверка не нужна или невозможна», тогда список не меняется.
 */
export const mineOf = (
  changed: readonly PackFileChange[],
  same: ReadonlySet<string> | null,
): PackFileChange[] =>
  same === null ? [...changed] : changed.filter((c) => !same.has(c.path));
