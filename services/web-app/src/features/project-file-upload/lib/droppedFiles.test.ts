import { describe, expect, it } from "vitest";
import { readDropped, snapshotDrop } from "./droppedFiles";

const fileEntry = (name: string): FileSystemEntry =>
  ({
    name,
    isFile: true,
    isDirectory: false,
    file: (resolve: (file: File) => void) => {
      resolve(new File(["x"], name));
    },
  }) as unknown as FileSystemEntry;

// Папка отдаёт детей двумя порциями, как Chrome, потом пусто.
const dirEntry = (
  name: string,
  children: FileSystemEntry[],
): FileSystemEntry => {
  const batches = [children.slice(0, 1), children.slice(1), []];
  return {
    name,
    isFile: false,
    isDirectory: true,
    createReader: () => ({
      readEntries: (resolve: (entries: FileSystemEntry[]) => void) => {
        resolve(batches.shift() ?? []);
      },
    }),
  } as unknown as FileSystemEntry;
};

const transfer = (
  items: { entry: FileSystemEntry | null; file?: File }[],
): DataTransfer =>
  ({
    items: items.map(({ entry, file }) => ({
      kind: "file",
      webkitGetAsEntry: () => entry,
      getAsFile: () => file ?? null,
    })),
    files: [],
    types: ["Files"],
  }) as unknown as DataTransfer;

describe("droppedFiles", () => {
  it("reads dropped folders recursively and keeps their structure", async () => {
    const dt = transfer([
      { entry: fileEntry("refs.bib") },
      {
        entry: dirEntry("scans", [
          fileEntry("a.png"),
          dirEntry("2026", [fileEntry("b.pdf")]),
          fileEntry("c.png"),
        ]),
      },
    ]);

    const entries = await readDropped(snapshotDrop(dt));

    expect(entries.map((e) => e.relPath)).toEqual([
      "refs.bib",
      "scans/a.png",
      "scans/2026/b.pdf",
      "scans/c.png",
    ]);
  });

  it("falls back to plain files when the browser gives no entries", async () => {
    const file = new File(["x"], "plain.png");
    const entries = await readDropped(
      snapshotDrop(transfer([{ entry: null, file }])),
    );
    expect(entries).toEqual([{ file, relPath: "plain.png" }]);
  });
});
