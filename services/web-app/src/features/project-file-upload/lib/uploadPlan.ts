// Разбор загрузки до отправки: куда ляжет каждый файл, что сервер точно не примет и что уже есть.
// Правила имён повторяют core/file_paths.py на бэкенде: отказ виден сразу, а не после отправки.

/** Файл с компьютера и его путь от папки назначения (POSIX, у папки целиком со вложенными папками). */
export type UploadEntry = {
  file: File;
  relPath: string;
};

/** Почему файл не уйдёт на сервер, ещё до отправки. */
export type ClientProblem =
  | "too_large"
  | "reserved"
  | "bad_name"
  | "too_long"
  | "quota"
  | "folder_conflict";

export type PlannedFile = {
  file: File;
  /** Путь от корня проекта. */
  path: string;
  size: number;
  problem: ClientProblem | null;
  /** Файл с таким путём уже есть в проекте: спросить «заменить, оставить оба, пропустить». */
  exists: boolean;
};

export type PlanLimits = {
  /** Предел одного файла (project.file_max_bytes); null: сервер его не сообщил. */
  maxFileBytes: number | null;
  /** Свободное место проекта в байтах; null: предел не ведётся (локальная Студия). */
  freeBytes: number | null;
};

const RESERVED_SEGMENTS = new Set([".hse-studio", ".git", ".build"]);
const MAX_SEGMENT_BYTES = 255;
const MAX_PATH_BYTES = 1024;
// Служебный мусор систем, который попадает в загрузку папки целиком; его не загружаем молча.
const JUNK_NAMES = new Set([".ds_store", "thumbs.db", "desktop.ini"]);
const JUNK_DIRS = new Set(["__macosx"]);

const encoder = new TextEncoder();
const byteLength = (value: string): number => encoder.encode(value).length;

// Управляющие символы (0x00-0x1F и 0x7F) в имени файла.
const hasControlChar = (value: string): boolean => {
  for (let i = 0; i < value.length; i += 1) {
    const code = value.charCodeAt(i);
    if (code < 0x20 || code === 0x7f) return true;
  }
  return false;
};

export const joinPath = (folder: string, rel: string): string => {
  const parts = [...folder.split("/"), ...rel.split("/")].filter(
    (part) => part !== "" && part !== ".",
  );
  return parts.join("/");
};

/** Системный мусор (.DS_Store, Thumbs.db, __MACOSX/): в проект не нужен. */
export const isJunkPath = (relPath: string): boolean => {
  const segments = relPath.split("/").filter(Boolean);
  const name = segments.at(-1)?.toLowerCase() ?? "";
  return (
    JUNK_NAMES.has(name) ||
    segments.some((segment) => JUNK_DIRS.has(segment.toLowerCase()))
  );
};

/** Имя, которое сервер отклонит (core/file_paths.py), или null. */
export const pathProblem = (path: string): ClientProblem | null => {
  const segments = path.split("/").filter((s) => s !== "" && s !== ".");
  if (segments.length === 0) return "bad_name";
  for (const segment of segments) {
    if (segment === "..") return "bad_name";
    if (segment.includes("\\") || hasControlChar(segment)) return "bad_name";
    if (RESERVED_SEGMENTS.has(segment.toLowerCase())) return "reserved";
    if (byteLength(segment) > MAX_SEGMENT_BYTES) return "too_long";
  }
  return byteLength(segments.join("/")) > MAX_PATH_BYTES ? "too_long" : null;
};

const splitName = (name: string): { stem: string; ext: string } => {
  const dot = name.lastIndexOf(".");
  return dot > 0
    ? { stem: name.slice(0, dot), ext: name.slice(dot) }
    : { stem: name, ext: "" };
};

/** «Оставить оба»: `рис.png` становится `рис (1).png`, `рис (2).png` и так далее, пока имя занято. */
export const freeCopyPath = (
  path: string,
  taken: ReadonlySet<string>,
): string => {
  const cut = path.lastIndexOf("/");
  const folder = cut >= 0 ? path.slice(0, cut + 1) : "";
  const { stem, ext } = splitName(path.slice(cut + 1));
  for (let n = 1; ; n += 1) {
    const candidate = `${folder}${stem} (${String(n)})${ext}`;
    if (!taken.has(candidate)) return candidate;
  }
};

/** Папки на пути к файлу: `a/b/c.png` даёт `a` и `a/b`. */
const ancestors = (path: string): string[] => {
  const segments = path.split("/");
  return segments
    .slice(0, -1)
    .map((_, index) => segments.slice(0, index + 1).join("/"));
};

/**
 * План загрузки: путь каждого файла от корня проекта, отказы до отправки и совпадения с тем,
 * что уже есть. Место проекта расходуется по порядку: файлы, которые уже не влезают, получают `quota`.
 */
export const planUpload = (
  entries: readonly UploadEntry[],
  destFolder: string,
  existing: { files: ReadonlySet<string>; dirs: ReadonlySet<string> },
  limits: PlanLimits,
): PlannedFile[] => {
  let free = limits.freeBytes;
  const seen = new Set<string>();
  const planned: PlannedFile[] = [];
  for (const { file, relPath } of entries) {
    if (isJunkPath(relPath)) continue;
    const path = joinPath(destFolder, relPath);
    // Два файла с одним путём в одной загрузке (папка и файл с тем же именем): берём первый.
    if (seen.has(path)) continue;
    seen.add(path);
    let problem: ClientProblem | null = pathProblem(path);
    if (
      problem === null &&
      (existing.dirs.has(path) ||
        ancestors(path).some((dir) => existing.files.has(dir)))
    ) {
      problem = "folder_conflict";
    }
    if (
      problem === null &&
      limits.maxFileBytes !== null &&
      file.size > limits.maxFileBytes
    ) {
      problem = "too_large";
    }
    if (problem === null && free !== null) {
      if (file.size > free) problem = "quota";
      else free -= file.size;
    }
    planned.push({
      file,
      path,
      size: file.size,
      problem,
      exists: problem === null && existing.files.has(path),
    });
  }
  return planned;
};

/** Файлы из `<input type="file">`: у выбора папки путь берётся из `webkitRelativePath`. */
export const entriesFromFileList = (files: Iterable<File>): UploadEntry[] =>
  [...files].map((file) => ({
    file,
    relPath: file.webkitRelativePath || file.name,
  }));
