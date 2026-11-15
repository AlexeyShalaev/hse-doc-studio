import type { UploadEntry } from "./uploadPlan";

// Перетаскивание с компьютера: файлы и папки целиком. Записи берутся из события сразу, пока
// оно живо (после `await` браузер очищает DataTransfer), а обход папок идёт уже асинхронно.

/** Что лежит в перетаскивании: запись файловой системы (файл или папка) или просто файл. */
export type DroppedSource =
  { kind: "entry"; entry: FileSystemEntry } | { kind: "file"; file: File };

/** Снимок перетаскивания; вызывать прямо в обработчике `drop`, до любого `await`. */
export const snapshotDrop = (dataTransfer: DataTransfer): DroppedSource[] => {
  const sources: DroppedSource[] = [];
  for (const item of Array.from(dataTransfer.items)) {
    if (item.kind !== "file") continue;
    const entry =
      typeof item.webkitGetAsEntry === "function"
        ? item.webkitGetAsEntry()
        : null;
    if (entry) {
      sources.push({ kind: "entry", entry });
      continue;
    }
    const file = item.getAsFile();
    if (file) sources.push({ kind: "file", file });
  }
  if (sources.length === 0) {
    for (const file of Array.from(dataTransfer.files)) {
      sources.push({ kind: "file", file });
    }
  }
  return sources;
};

const isFileEntry = (entry: FileSystemEntry): entry is FileSystemFileEntry =>
  entry.isFile;

const isDirectoryEntry = (
  entry: FileSystemEntry,
): entry is FileSystemDirectoryEntry => entry.isDirectory;

const readFile = (entry: FileSystemFileEntry): Promise<File> =>
  new Promise((resolve, reject) => {
    entry.file(resolve, reject);
  });

// `readEntries` отдаёт содержимое папки порциями (в Chrome по 100): читаем, пока не вернёт пусто.
const readChildren = async (
  directory: FileSystemDirectoryEntry,
): Promise<FileSystemEntry[]> => {
  const reader = directory.createReader();
  const children: FileSystemEntry[] = [];
  for (;;) {
    const batch = await new Promise<FileSystemEntry[]>((resolve, reject) => {
      reader.readEntries(resolve, reject);
    });
    if (batch.length === 0) return children;
    children.push(...batch);
  }
};

const collect = async (
  entry: FileSystemEntry,
  prefix: string,
  out: UploadEntry[],
): Promise<void> => {
  if (isFileEntry(entry)) {
    out.push({
      file: await readFile(entry),
      relPath: `${prefix}${entry.name}`,
    });
    return;
  }
  if (!isDirectoryEntry(entry)) return;
  for (const child of await readChildren(entry)) {
    await collect(child, `${prefix}${entry.name}/`, out);
  }
};

/** Все файлы перетаскивания с путями от места, куда их бросили; папки раскрываются со структурой. */
export const readDropped = async (
  sources: readonly DroppedSource[],
): Promise<UploadEntry[]> => {
  const out: UploadEntry[] = [];
  for (const source of sources) {
    if (source.kind === "file") {
      out.push({ file: source.file, relPath: source.file.name });
    } else {
      await collect(source.entry, "", out);
    }
  }
  return out;
};
