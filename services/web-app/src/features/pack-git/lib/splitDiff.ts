import { countChanges, type DiffPatchFile, type DiffStat } from "@shared/ui";

// Единый diff от базы (GET .../git/diff) делится на файлы для показа по одному:
// каждый кусок начинается с «diff --git a/<путь> b/<путь>».

export type DiffFile = DiffPatchFile & { stat: DiffStat };

const HEADER = /^diff --git a\/(.+?) b\/(.+)$/;

const changeOf = (lines: readonly string[]): string => {
  for (const line of lines) {
    if (line.startsWith("new file mode")) return "A";
    if (line.startsWith("deleted file mode")) return "D";
    if (line.startsWith("rename from")) return "R";
    if (line.startsWith("@@")) break;
  }
  return "M";
};

/** Кусок diff одного файла: путь (новый, у удалённого старый), буква изменения, текст. */
export const splitDiff = (text: string): DiffFile[] => {
  const files: DiffFile[] = [];
  let current: { path: string; lines: string[] } | null = null;
  const flush = () => {
    if (!current) return;
    const patch = current.lines.join("\n");
    const binary = current.lines.some(
      (line) => line.startsWith("Binary files ") || line === "GIT binary patch",
    );
    const change = changeOf(current.lines);
    files.push({
      path: current.path,
      change,
      patch,
      binary,
      stat: binary ? { add: 0, del: 0 } : countChanges(patch),
    });
  };
  for (const line of text.split("\n")) {
    const header = HEADER.exec(line);
    if (header) {
      flush();
      current = { path: header[2] ?? header[1] ?? "", lines: [line] };
    } else if (current) {
      current.lines.push(line);
    }
  }
  flush();
  return files;
};
