import { describe, expect, it } from "vitest";
import { diffHunks, diffLines } from "./lineDiff";

const kinds = (text: string, other: string) =>
  diffLines(text, other).map((line) => `${line.kind}:${line.text}`);

describe("diffLines", () => {
  it("одинаковые тексты дают только контекст", () => {
    expect(kinds("a\nb", "a\nb")).toEqual(["context:a", "context:b"]);
  });

  it("вставленная строка помечается как добавление", () => {
    expect(kinds("a\nc", "a\nb\nc")).toEqual([
      "context:a",
      "add:b",
      "context:c",
    ]);
  });

  it("удалённая строка помечается как удаление", () => {
    expect(kinds("a\nb\nc", "a\nc")).toEqual([
      "context:a",
      "del:b",
      "context:c",
    ]);
  });

  it("изменённая строка — это удаление плюс добавление", () => {
    expect(kinds("a\nb", "a\nB")).toEqual(["context:a", "del:b", "add:B"]);
  });

  it("нумерует строки по своей стороне", () => {
    const [, added] = diffLines("a\nc", "a\nb\nc");
    expect(added).toEqual({ kind: "add", text: "b", leftNo: null, rightNo: 2 });
  });

  it("пустой текст против непустого — сплошное добавление", () => {
    expect(kinds("", "a")).toEqual(["del:", "add:a"]);
  });
});

describe("diffHunks", () => {
  it("без изменений участков нет", () => {
    expect(diffHunks(diffLines("a\nb", "a\nb"))).toEqual([]);
  });

  it("склеивает соседние правки в один участок", () => {
    const lines = diffLines("a\nb\nc\nd", "a\nB\nc\nD");
    expect(diffHunks(lines, 1)).toHaveLength(1);
  });

  it("далёкие правки остаются разными участками", () => {
    const left = ["x", ...Array(20).fill("same"), "y"].join("\n");
    const right = ["X", ...Array(20).fill("same"), "Y"].join("\n");

    expect(diffHunks(diffLines(left, right), 2)).toHaveLength(2);
  });

  it("вокруг правки остаётся контекст", () => {
    const lines = diffLines("a\nb\nc\nd\ne", "a\nb\nC\nd\ne");
    const [hunk] = diffHunks(lines, 1);

    expect(hunk?.map((line) => line.text)).toEqual(["b", "c", "C", "d"]);
  });
});
