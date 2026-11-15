import { describe, expect, it } from "vitest";
import {
  entriesFromFileList,
  freeCopyPath,
  isJunkPath,
  joinPath,
  pathProblem,
  planUpload,
  type UploadEntry,
} from "./uploadPlan";

const fileOf = (name: string, size = 4): File =>
  new File([new Uint8Array(size)], name, { type: "image/png" });

const entry = (relPath: string, size = 4): UploadEntry => ({
  file: fileOf(relPath.split("/").pop() ?? relPath, size),
  relPath,
});

const NONE = { files: new Set<string>(), dirs: new Set<string>() };
const NO_LIMITS = { maxFileBytes: null, freeBytes: null };

describe("uploadPlan", () => {
  it("joins the destination folder and the relative path", () => {
    expect(joinPath("", "a.png")).toBe("a.png");
    expect(joinPath("vkr/images", "scans/a.png")).toBe(
      "vkr/images/scans/a.png",
    );
    expect(joinPath("vkr/", "./a.png")).toBe("vkr/a.png");
  });

  it("mirrors the server rules for names", () => {
    expect(pathProblem("vkr/images/рис 1.png")).toBeNull();
    expect(pathProblem(".gitignore")).toBeNull();
    expect(pathProblem("../x.png")).toBe("bad_name");
    expect(pathProblem("a\\b.png")).toBe("bad_name");
    expect(pathProblem("a\nb.png")).toBe("bad_name");
    expect(pathProblem(".hse-studio/project.json")).toBe("reserved");
    expect(pathProblem("vkr/.GIT/config")).toBe("reserved");
    expect(pathProblem(".build/x.aux")).toBe("reserved");
    expect(pathProblem(`${"я".repeat(200)}.png`)).toBe("too_long");
  });

  it("drops system junk from folder uploads", () => {
    expect(isJunkPath("scans/.DS_Store")).toBe(true);
    expect(isJunkPath("Thumbs.db")).toBe(true);
    expect(isJunkPath("__MACOSX/scans/a.png")).toBe(true);
    expect(isJunkPath("scans/a.png")).toBe(false);
  });

  it("finds a free name for «keep both»", () => {
    const taken = new Set(["img/a.png", "img/a (1).png", "notes"]);
    expect(freeCopyPath("img/a.png", taken)).toBe("img/a (2).png");
    expect(freeCopyPath("notes", taken)).toBe("notes (1)");
    expect(freeCopyPath("archive.tar.gz", taken)).toBe("archive.tar (1).gz");
  });

  it("takes the folder structure from webkitRelativePath", () => {
    const flat = fileOf("a.png");
    const nested = fileOf("b.png");
    Object.defineProperty(nested, "webkitRelativePath", {
      value: "scans/2026/b.png",
    });
    expect(entriesFromFileList([flat, nested]).map((e) => e.relPath)).toEqual([
      "a.png",
      "scans/2026/b.png",
    ]);
  });

  it("marks existing files, folder clashes, oversize and bad names", () => {
    const existing = {
      files: new Set(["img/a.png", "notes.txt"]),
      dirs: new Set(["img", "img/sub"]),
    };
    const plan = planUpload(
      [
        entry("a.png"),
        entry("new.png"),
        entry("sub"),
        entry("big.pdf", 11),
        entry(".git/hooks/x"),
        entry("scans/.DS_Store"),
      ],
      "img",
      existing,
      { maxFileBytes: 10, freeBytes: null },
    );
    expect(plan.map((p) => [p.path, p.problem, p.exists])).toEqual([
      ["img/a.png", null, true],
      ["img/new.png", null, false],
      ["img/sub", "folder_conflict", false],
      ["img/big.pdf", "too_large", false],
      ["img/.git/hooks/x", "reserved", false],
    ]);
    const underFile = planUpload(
      [entry("notes.txt/x.png")],
      "",
      existing,
      NO_LIMITS,
    );
    expect(underFile[0]?.problem).toBe("folder_conflict");
  });

  it("spends the free project space in order", () => {
    const plan = planUpload(
      [entry("a.png", 6), entry("b.png", 6), entry("c.png", 3)],
      "",
      NONE,
      { maxFileBytes: null, freeBytes: 10 },
    );
    expect(plan.map((p) => p.problem)).toEqual([null, "quota", null]);
  });
});
