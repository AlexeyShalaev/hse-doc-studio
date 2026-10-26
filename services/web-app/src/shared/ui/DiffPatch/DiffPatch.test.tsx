import { render, screen } from "@testing-library/react";
import { beforeEach, describe, expect, it } from "vitest";
import { i18n } from "@shared/lib/i18n";
import { DiffPatch, changeMeta, countChanges, parsePatch } from ".";

const PATCH = [
  "diff --git a/a.tex b/a.tex",
  "index 111..222 100644",
  "--- a/a.tex",
  "+++ b/a.tex",
  "@@ -3,3 +3,4 @@ intro",
  " keep",
  "-old line",
  "+new line",
  "+extra line",
  "@@ -20 +21 @@",
  "-tail",
  "\\ No newline at end of file",
  "+tail2",
].join("\n");

describe("parsePatch", () => {
  it("skips file headers and numbers lines on both sides", () => {
    const hunks = parsePatch(PATCH);
    expect(hunks.map((h) => h.header)).toEqual([
      "@@ -3,3 +3,4 @@ intro",
      "@@ -20 +21 @@",
    ]);
    expect(hunks[0]?.lines).toEqual([
      { kind: "context", text: "keep", oldNo: 3, newNo: 3 },
      { kind: "del", text: "old line", oldNo: 4, newNo: null },
      { kind: "add", text: "new line", oldNo: null, newNo: 4 },
      { kind: "add", text: "extra line", oldNo: null, newNo: 5 },
    ]);
    expect(hunks[1]?.lines.map((l) => l.kind)).toEqual(["del", "meta", "add"]);
    expect(hunks[1]?.lines[0]).toMatchObject({ oldNo: 20 });
    expect(hunks[1]?.lines[2]).toMatchObject({ newNo: 21 });
  });

  it("returns nothing for an empty patch", () => {
    expect(parsePatch("")).toEqual([]);
  });
});

describe("countChanges", () => {
  it("counts added and removed lines, not the +++/--- headers", () => {
    expect(countChanges(PATCH)).toEqual({ add: 3, del: 2 });
    expect(countChanges("")).toEqual({ add: 0, del: 0 });
  });
});

describe("DiffPatch", () => {
  beforeEach(async () => {
    await i18n.changeLanguage("ru");
  });

  it("shows status letter, path, counts and numbered lines", () => {
    const { container } = render(
      <DiffPatch
        file={{ path: "a.tex", change: "M", patch: PATCH, binary: false }}
        stat={countChanges(PATCH)}
      />,
    );
    expect(screen.getByTitle("изменён")).toHaveTextContent("M");
    expect(screen.getByTitle("a.tex")).toBeVisible();
    expect(screen.getByText("+3")).toHaveStyle({ color: "var(--c-ok)" });
    expect(screen.getByText("−2")).toHaveStyle({ color: "var(--c-err)" });
    expect(screen.getByText("new line")).toBeInTheDocument();
    expect(container.querySelectorAll('[data-kind="add"]')).toHaveLength(3);
    expect(container.querySelectorAll('[data-kind="del"]')).toHaveLength(2);
  });

  it("explains binary files and empty diffs", () => {
    const { rerender } = render(
      <DiffPatch
        file={{ path: "i.png", change: "A", patch: "", binary: true }}
        stat={{ add: 0, del: 0 }}
      />,
    );
    expect(screen.getByText(/Бинарный файл/)).toBeVisible();
    expect(screen.queryByText("+0")).toBeNull();
    rerender(
      <DiffPatch
        file={{ path: "e.tex", change: "R", patch: "", binary: false }}
        stat={{ add: 0, del: 0 }}
      />,
    );
    expect(screen.getByText(/Нет текстовых изменений/)).toBeVisible();
  });

  it("follows the interface language", async () => {
    await i18n.changeLanguage("en");
    render(
      <DiffPatch
        file={{ path: "i.png", change: "D", patch: "", binary: true }}
        stat={{ add: 0, del: 0 }}
      />,
    );
    expect(screen.getByText(/Binary file/)).toBeVisible();
    expect(screen.getByTitle("deleted")).toHaveTextContent("D");
  });

  it("limits the height of long diffs", () => {
    const { container } = render(
      <DiffPatch
        file={{ path: "a.tex", change: "M", patch: PATCH, binary: false }}
        stat={countChanges(PATCH)}
        maxHeight={200}
      />,
    );
    expect(container.querySelector(".vcs-diff")).toHaveStyle({
      maxHeight: "200px",
    });
  });
});

describe("changeMeta", () => {
  it("keeps unknown statuses neutral", () => {
    expect(changeMeta("T")).toMatchObject({
      letter: "T",
      label: "T",
      color: "var(--fg-2)",
    });
  });
});
