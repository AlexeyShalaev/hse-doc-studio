import { readFileSync } from "node:fs";
import { join } from "node:path";
import { describe, expect, it } from "vitest";
import {
  PackGitSchema,
  PackWorkspaceSchema,
  type PackGit,
  type PackWorkspace,
} from "@entities/pack-studio";
import {
  pickContinueId,
  unsentCount,
  workspaceStatus,
} from "./workspaceStatus";

const FIXTURES = join(
  import.meta.dirname,
  "../../../../../../contracts/pack-studio/fixtures",
);
const read = (dir: string, name: string): unknown =>
  JSON.parse(readFileSync(join(FIXTURES, dir, `${name}.json`), "utf8"));
const ws = (
  name: string,
  patch: Partial<PackWorkspace> = {},
): PackWorkspace => ({
  ...PackWorkspaceSchema.parse(read("PackWorkspace", name)),
  ...patch,
});
const gitOf = (
  workspace: PackWorkspace,
  patch: Partial<PackGit> = {},
): PackGit => ({
  ...PackGitSchema.parse(read("PackGit", "detached_dirty")),
  workspace,
  ...patch,
});

const ready = ws("git_ready");
const clean = (w: PackWorkspace) =>
  gitOf(w, { uncommitted: [], changed: [], dirty: false });

describe("workspaceStatus", () => {
  it.each([
    ["подключается", ws("git_cloning"), undefined, { kind: "cloning" }],
    ["не удалось", ws("git_failed"), undefined, { kind: "failed" }],
    ["обновляется", { ...ready, busy: true }, undefined, { kind: "fetching" }],
    ["папка", ws("folder"), undefined, { kind: "folder" }],
    ["git ещё не пришёл", ready, undefined, { kind: "unknown" }],
    ["чисто", ready, clean(ready), { kind: "clean" }],
    ["не отправлено", ready, gitOf(ready), { kind: "unsent", unsent: 2 }],
  ] as const)("%s", (_name, workspace, git, expected) => {
    expect(workspaceStatus(workspace, git)).toEqual(expected);
  });

  it("запрос открыт: считаются только правки после него", () => {
    const proposed = ws("git_proposed");
    expect(workspaceStatus(proposed, clean(proposed))).toEqual({
      kind: "request",
      number: 412,
      unsent: 0,
    });
    expect(workspaceStatus(proposed, gitOf(proposed))).toEqual({
      kind: "request",
      number: 412,
      unsent: 2,
    });
    // Пока git не пришёл, число правок не придумывается.
    expect(workspaceStatus(proposed, undefined)).toEqual({
      kind: "request",
      number: 412,
      unsent: 0,
    });
  });

  it("unsentCount: без запроса всё, что отличается от основной ветки", () => {
    const g = gitOf(ready, {
      uncommitted: [],
      changed: [
        { path: "a", status: "modified" },
        { path: "b", status: "added" },
        { path: "c", status: "deleted" },
      ],
    });
    expect(unsentCount(g, ready)).toBe(3);
    expect(unsentCount(g, ws("git_proposed"))).toBe(0);
  });
});

describe("pickContinueId", () => {
  const a = { ...ready, id: "a", updated_at: "2026-11-10T10:00:00Z" };
  const b = { ...ready, id: "b", updated_at: "2026-11-12T10:00:00Z" };
  const c = { ...ready, id: "c", updated_at: "2026-11-11T10:00:00Z" };
  const folder = { ...ws("folder"), id: "f" };
  const failed = { ...ws("git_failed"), id: "x" };
  const gits = (...dirty: PackWorkspace[]) =>
    new Map(
      [a, b, c].map((w) => [
        w.id,
        dirty.some((d) => d.id === w.id) ? gitOf(w) : clean(w),
      ]),
    );

  it("ничего не открывали и правок нет: главная кнопка экрана «Подключить»", () => {
    expect(pickContinueId([a, b, folder, failed], gits(), null)).toBeNull();
  });

  it("последнее открытое готовое пространство", () => {
    expect(pickContinueId([a, b], gits(), "a")).toBe("a");
    // Удалённое или неготовое «последнее» не предлагается.
    expect(pickContinueId([a, b], gits(), "gone")).toBeNull();
    expect(pickContinueId([a, failed], gits(), "x")).toBeNull();
  });

  it("неотправленные правки важнее последнего открытого", () => {
    expect(pickContinueId([a, b], gits(b), "a")).toBe("b");
  });

  it("из нескольких с правками: последнее открытое, иначе самое свежее", () => {
    expect(pickContinueId([a, b, c], gits(a, b, c), "c")).toBe("c");
    expect(pickContinueId([a, b, c], gits(a, b, c), null)).toBe("b");
    expect(pickContinueId([a, b, c], gits(a, c), "b")).toBe("c");
  });
});
