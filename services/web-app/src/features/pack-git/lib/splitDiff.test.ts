import { describe, expect, it } from "vitest";
import { splitDiff } from "./splitDiff";

const DIFF = [
  "diff --git a/packs/demo/pack.yaml b/packs/demo/pack.yaml",
  "--- a/packs/demo/pack.yaml",
  "+++ b/packs/demo/pack.yaml",
  "@@ -1 +1 @@",
  "-id: demo",
  "+id: demo # правка",
  "diff --git a/packs/demo/notes.tex b/packs/demo/notes.tex",
  "new file mode 100644",
  "--- /dev/null",
  "+++ b/packs/demo/notes.tex",
  "@@ -0,0 +1,2 @@",
  "+a",
  "+b",
  "diff --git a/packs/demo/logo.png b/packs/demo/logo.png",
  "deleted file mode 100644",
  "Binary files a/packs/demo/logo.png and /dev/null differ",
  "",
].join("\n");

describe("splitDiff", () => {
  it("делит единый diff на файлы с буквой изменения и счётчиками", () => {
    const files = splitDiff(DIFF);
    expect(files.map((f) => [f.path, f.change, f.binary])).toEqual([
      ["packs/demo/pack.yaml", "M", false],
      ["packs/demo/notes.tex", "A", false],
      ["packs/demo/logo.png", "D", true],
    ]);
    expect(files[0]?.stat).toEqual({ add: 1, del: 1 });
    expect(files[1]?.stat).toEqual({ add: 2, del: 0 });
  });

  it("пустой diff даёт пустой список", () => {
    expect(splitDiff("")).toEqual([]);
  });
});
