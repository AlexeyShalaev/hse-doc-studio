import { describe, expect, it } from "vitest";
import type {
  ConflictFile,
  ConflictSession,
  FileResolution,
} from "@entities/git-sync";
import {
  carryOverDrafts,
  chooseAllHunks,
  clearHunkChoice,
  composeText,
  draftsFromSession,
  fileProgress,
  hasConflictMarkers,
  hunkResultLines,
  nextOpenHunkKey,
  nextOpenPath,
  openHunkKeys,
  pruneResolution,
  sessionProgress,
  setFileChoice,
  setHunkChoice,
  setManualText,
  type TextDetail,
} from "./conflictModel";

const side = { exists: true, size: 10, author: "Я", at: null };

const file = (overrides: Partial<ConflictFile>): ConflictFile => ({
  path: "a.tex",
  owner: null,
  kind: "text",
  action: "conflict",
  conflict_type: "content",
  hunks: 0,
  open_hunks: 0,
  fields: 0,
  open_fields: 0,
  resolved: false,
  resolution: null,
  allowed: ["mine", "theirs"],
  default_resolution: null,
  sides: { ours: side, theirs: side, base: side },
  copy_path: null,
  doc_id: null,
  ...overrides,
});

const sessionOf = (files: ConflictFile[]): ConflictSession => ({
  id: "s1",
  fingerprint: "f1",
  ours: { commit: "o", author: "Я", at: null, message: null },
  theirs: { commit: "t", author: "Она", at: null, message: null },
  base: null,
  counts: { conflict: files.length, auto: 0, total: files.length },
  unresolved: files.length,
  drafts_saved_at: null,
  warnings: [],
  files,
});

const detail: TextDetail = {
  kind: "text",
  eol: "lf",
  truncated: false,
  segments: [
    { type: "clean", lines: ["a", "b"] },
    {
      type: "hunk",
      key: "k1",
      ours: ["mine1"],
      base: ["base1"],
      theirs: ["theirs1", "theirs2"],
      ours_start: 3,
      result_start: 3,
    },
    { type: "clean", lines: ["c"] },
    {
      type: "hunk",
      key: "k2",
      ours: ["mine2"],
      base: [],
      theirs: ["theirs3"],
      ours_start: 5,
      result_start: 6,
    },
  ],
};

describe("hunk choices", () => {
  it("adds, replaces and clears a choice by key", () => {
    const first = setHunkChoice(null, "k1", { choice: "mine" });
    const second = setHunkChoice(first, "k2", { choice: "theirs" });
    expect(second).toEqual({
      kind: "hunks",
      hunks: { k1: { choice: "mine" }, k2: { choice: "theirs" } },
    });
    const changed = setHunkChoice(second, "k1", { choice: "both" });
    expect(changed.kind === "hunks" && changed.hunks.k1).toEqual({
      choice: "both",
    });
    // Пустое решение остаётся: сервер должен узнать, что выбор снят.
    expect(
      clearHunkChoice(setHunkChoice(null, "k1", { choice: "mine" }), "k1"),
    ).toEqual({ kind: "hunks", hunks: {} });
  });

  it("drops a whole-file or manual resolution when a hunk is chosen", () => {
    const manual: FileResolution = setManualText("x");
    expect(setHunkChoice(manual, "k1", { choice: "mine" })).toEqual({
      kind: "hunks",
      hunks: { k1: { choice: "mine" } },
    });
  });

  it("chooses every hunk of a file at once", () => {
    expect(chooseAllHunks(detail, "theirs")).toEqual({
      kind: "hunks",
      hunks: { k1: { choice: "theirs" }, k2: { choice: "theirs" } },
    });
  });

  it("lists the open hunks in file order", () => {
    expect(openHunkKeys(detail, null)).toEqual(["k1", "k2"]);
    expect(
      openHunkKeys(detail, setHunkChoice(null, "k1", { choice: "mine" })),
    ).toEqual(["k2"]);
  });
});

describe("progress", () => {
  it("counts hunks of a text file against the saved choices", () => {
    const f = file({ hunks: 3, open_hunks: 3 });
    expect(fileProgress(f, null)).toEqual({
      resolved: false,
      open: 3,
      total: 3,
    });
    const partial = setHunkChoice(null, "k1", { choice: "mine" });
    expect(fileProgress(f, partial)).toEqual({
      resolved: false,
      open: 2,
      total: 3,
    });
    const all: FileResolution = {
      kind: "hunks",
      hunks: {
        k1: { choice: "mine" },
        k2: { choice: "mine" },
        k3: { choice: "mine" },
      },
    };
    expect(fileProgress(f, all).resolved).toBe(true);
  });

  it("does not count a choice for a hunk the file no longer has", () => {
    const f = file({ hunks: 2, open_hunks: 2 });
    const stale: FileResolution = {
      kind: "hunks",
      hunks: { k1: { choice: "mine" }, gone: { choice: "mine" } },
    };
    expect(fileProgress(f, stale, ["k1", "k2"]).open).toBe(1);
  });

  it("treats a whole-file choice as resolved only when it is allowed", () => {
    const f = file({ kind: "binary", allowed: ["mine", "theirs", "newest"] });
    expect(fileProgress(f, setFileChoice("newest")).resolved).toBe(true);
    expect(fileProgress(f, setFileChoice("both")).resolved).toBe(false);
  });

  it("treats a manual text as resolved", () => {
    const f = file({ hunks: 3, open_hunks: 3 });
    expect(fileProgress(f, setManualText("done")).resolved).toBe(true);
  });

  it("cannot resolve a file without hunks by a hunk resolution", () => {
    const f = file({ hunks: 0, conflict_type: "deleted_by_them" });
    expect(fileProgress(f, { kind: "hunks", hunks: {} }).resolved).toBe(false);
  });

  it("trusts the server for a file without a local choice", () => {
    expect(fileProgress(file({ resolved: true }), null).resolved).toBe(true);
  });

  it("ignores files the server resolved on its own", () => {
    const auto = file({ path: "auto.tex", action: "merged", resolved: true });
    expect(fileProgress(auto, null)).toEqual({
      resolved: true,
      open: 0,
      total: 0,
    });
  });

  it("sums up a session", () => {
    const session = sessionOf([
      file({ path: "a.tex", hunks: 2, open_hunks: 2 }),
      file({ path: "b.json", kind: "json", fields: 1, open_fields: 1 }),
      file({ path: "c.png", kind: "binary", allowed: ["mine", "theirs"] }),
      file({ path: "d.tex", action: "merged", resolved: true }),
    ]);
    const progress = sessionProgress(session, {
      "c.png": setFileChoice("mine"),
    });
    expect(progress).toEqual({
      total: 3,
      resolved: 1,
      open: 2,
      openItems: 3,
      openPaths: ["a.tex", "b.json"],
    });
  });
});

describe("navigation", () => {
  it("finds the next open hunk, wrapping around", () => {
    const resolution = setHunkChoice(null, "k1", { choice: "mine" });
    expect(nextOpenHunkKey(detail, resolution, "k1")).toBe("k2");
    expect(nextOpenHunkKey(detail, resolution, "k2")).toBe("k2");
    expect(nextOpenHunkKey(detail, null, "k2")).toBe("k1");
    expect(nextOpenHunkKey(detail, null, "k1", -1)).toBe("k2");
    expect(nextOpenHunkKey(detail, null, null)).toBe("k1");
    expect(nextOpenHunkKey(detail, null, null, -1)).toBe("k2");
  });

  it("returns null when nothing is open", () => {
    expect(
      nextOpenHunkKey(detail, chooseAllHunks(detail, "mine"), "k1"),
    ).toBeNull();
  });

  it("finds the next unresolved file", () => {
    const session = sessionOf([
      file({ path: "a", hunks: 1, open_hunks: 1 }),
      file({ path: "b", hunks: 1, open_hunks: 1 }),
      file({ path: "c", hunks: 1, open_hunks: 1 }),
    ]);
    const drafts = { b: setHunkChoice(null, "x", { choice: "mine" }) };
    expect(nextOpenPath(session, drafts, "a")).toBe("c");
    expect(nextOpenPath(session, drafts, "c")).toBe("a");
    expect(nextOpenPath(session, drafts, "a", -1)).toBe("c");
    expect(
      nextOpenPath(
        session,
        {
          a: setManualText("1"),
          b: setManualText("2"),
          c: setManualText("3"),
        },
        "a",
      ),
    ).toBeNull();
  });
});

describe("result text", () => {
  it("keeps mine for hunks without a choice", () => {
    expect(composeText(detail, null)).toBe("a\nb\nmine1\nc\nmine2");
  });

  it("applies every kind of choice", () => {
    const hunk = detail.segments[1];
    if (hunk?.type !== "hunk") throw new Error("fixture");
    expect(hunkResultLines(hunk, { choice: "theirs" })).toEqual([
      "theirs1",
      "theirs2",
    ]);
    expect(hunkResultLines(hunk, { choice: "both" })).toEqual([
      "mine1",
      "theirs1",
      "theirs2",
    ]);
    expect(hunkResultLines(hunk, { choice: "both_reverse" })).toEqual([
      "theirs1",
      "theirs2",
      "mine1",
    ]);
    expect(hunkResultLines(hunk, { choice: "base" })).toEqual(["base1"]);
    expect(hunkResultLines(hunk, { choice: "custom", text: "x\ny" })).toEqual([
      "x",
      "y",
    ]);
  });

  it("composes the file from the choices and keeps CRLF", () => {
    const resolution: FileResolution = {
      kind: "hunks",
      hunks: { k1: { choice: "theirs" }, k2: { choice: "both" } },
    };
    expect(composeText(detail, resolution)).toBe(
      "a\nb\ntheirs1\ntheirs2\nc\nmine2\ntheirs3",
    );
    expect(composeText({ ...detail, eol: "crlf" }, null)).toBe(
      "a\r\nb\r\nmine1\r\nc\r\nmine2",
    );
  });

  it("returns a manual text as is", () => {
    expect(composeText(detail, setManualText("my text"))).toBe("my text");
  });

  it("recognises conflict markers", () => {
    expect(hasConflictMarkers("a\n<<<<<<< hse:ours\nb")).toBe(true);
    expect(hasConflictMarkers("a\n>>>>>>> hse:theirs")).toBe(true);
    expect(hasConflictMarkers("a\n||||||| hse:base\n")).toBe(true);
    expect(hasConflictMarkers("Title\n=======\ntext")).toBe(false);
    expect(hasConflictMarkers("x <<<<<<< y")).toBe(false);
    expect(hasConflictMarkers("a\nb")).toBe(false);
  });
});

describe("a rebuilt session", () => {
  it("keeps choices only for files that still conflict", () => {
    const session = sessionOf([
      file({ path: "a", hunks: 1 }),
      file({ path: "gone", action: "merged" }),
    ]);
    const drafts = {
      a: setHunkChoice(null, "k", { choice: "mine" }),
      gone: setFileChoice("mine"),
      removed: setFileChoice("mine"),
    };
    expect(Object.keys(carryOverDrafts(drafts, session))).toEqual(["a"]);
  });

  it("drops a whole-file choice that is no longer allowed", () => {
    const session = sessionOf([
      file({ path: "p", kind: "binary", allowed: ["mine"] }),
    ]);
    expect(carryOverDrafts({ p: setFileChoice("theirs") }, session)).toEqual(
      {},
    );
  });

  it("prunes choices for hunks that are gone", () => {
    const resolution: FileResolution = {
      kind: "hunks",
      hunks: { k1: { choice: "mine" }, old: { choice: "theirs" } },
    };
    expect(pruneResolution(resolution, detail)).toEqual({
      kind: "hunks",
      hunks: { k1: { choice: "mine" } },
    });
    const same: FileResolution = {
      kind: "hunks",
      hunks: { k1: { choice: "mine" } },
    };
    expect(pruneResolution(same, detail)).toBe(same);
  });

  it("starts from the drafts the server saved", () => {
    const saved = setHunkChoice(null, "k1", { choice: "theirs" });
    const session = sessionOf([
      file({ path: "a", hunks: 2, resolution: saved }),
      file({ path: "b", hunks: 1 }),
    ]);
    expect(draftsFromSession(session)).toEqual({ a: saved });
  });
});
