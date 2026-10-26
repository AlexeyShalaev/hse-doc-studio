import { describe, expect, it } from "vitest";
import {
  AUTHOR_ALL,
  AUTHOR_MINE,
  EMPTY_VCS_FILTERS,
  buildHistoryParams,
  dateWindow,
  isIncomingOnly,
  isOwnCommit,
  isVcsFiltersActive,
  kindChipIds,
  recentTotal,
  resolveKinds,
} from "./vcsHistoryFilters.model";

const FACETS = {
  edit: 40,
  compile: 12,
  manual: 3,
  sync: 2,
  template_update: 1,
  future_kind: 4,
  another_future: 1,
};

const NOON = new Date(2026, 9, 26, 12, 30);

describe("isVcsFiltersActive", () => {
  it("is false for the empty state and true for any condition", () => {
    expect(isVcsFiltersActive(EMPTY_VCS_FILTERS)).toBe(false);
    expect(isVcsFiltersActive({ ...EMPTY_VCS_FILTERS, query: " " })).toBe(
      false,
    );
    expect(isVcsFiltersActive({ ...EMPTY_VCS_FILTERS, query: "рис" })).toBe(
      true,
    );
    expect(isVcsFiltersActive({ ...EMPTY_VCS_FILTERS, kinds: ["edit"] })).toBe(
      true,
    );
    expect(
      isVcsFiltersActive({ ...EMPTY_VCS_FILTERS, author: AUTHOR_MINE }),
    ).toBe(true);
    expect(isVcsFiltersActive({ ...EMPTY_VCS_FILTERS, sync: "incoming" })).toBe(
      true,
    );
    expect(isVcsFiltersActive({ ...EMPTY_VCS_FILTERS, preset: "7d" })).toBe(
      true,
    );
  });
});

describe("kindChipIds", () => {
  it("lists known kinds that occur, in a stable order, and folds unknown kinds into other", () => {
    expect(kindChipIds(FACETS)).toEqual([
      { kind: "edit", count: 40 },
      { kind: "compile", count: 12 },
      { kind: "template_update", count: 1 },
      { kind: "sync", count: 2 },
      { kind: "other", count: 5 },
    ]);
  });

  it("never offers the named-version kind and skips kinds that do not occur", () => {
    const chips = kindChipIds({ manual: 5, edit: 1 });
    expect(chips.map((c) => c.kind)).toEqual(["edit"]);
  });

  it("keeps a selected kind visible even when its count dropped to zero", () => {
    expect(kindChipIds({ edit: 1 }, ["restore", "other"])).toEqual([
      { kind: "edit", count: 1 },
      { kind: "restore", count: 0 },
      { kind: "other", count: 0 },
    ]);
  });
});

describe("recentTotal", () => {
  it("counts everything except named versions", () => {
    expect(recentTotal(FACETS)).toBe(40 + 12 + 2 + 1 + 4 + 1);
  });
});

describe("resolveKinds", () => {
  it("asks for every kind but the named one when nothing is selected", () => {
    expect(resolveKinds([], FACETS)).toEqual([
      "edit",
      "compile",
      "sync",
      "template_update",
      "future_kind",
      "another_future",
    ]);
  });

  it("sends nothing before the facets arrive", () => {
    expect(resolveKinds([], undefined)).toBeUndefined();
  });

  it("expands other into every unknown kind and keeps the selected ones", () => {
    expect(resolveKinds(["edit", "other"], FACETS)).toEqual([
      "edit",
      "future_kind",
      "another_future",
    ]);
  });

  it("does not turn an empty other into a request for everything", () => {
    expect(resolveKinds(["other"], { edit: 2 })).toBeUndefined();
  });
});

describe("dateWindow", () => {
  it("starts presets at midnight so the request does not change every second", () => {
    const today = dateWindow({ preset: "today", from: "", to: "" }, NOON);
    expect(new Date(today.since ?? "").getHours()).toBe(0);
    expect(today.until).toBeUndefined();
    const week = dateWindow({ preset: "7d", from: "", to: "" }, NOON);
    expect(new Date(week.since ?? "").getDate()).toBe(19);
    const later = new Date(2026, 9, 26, 23, 59);
    expect(dateWindow({ preset: "7d", from: "", to: "" }, later)).toEqual(week);
  });

  it("covers the whole last day of a custom range", () => {
    const window = dateWindow(
      { preset: "custom", from: "2026-10-01", to: "2026-10-05" },
      NOON,
    );
    expect(new Date(window.since ?? "").getDate()).toBe(1);
    const until = new Date(window.until ?? "");
    expect(until.getDate()).toBe(5);
    expect(until.getHours()).toBe(23);
  });

  it("allows an open-ended custom range and no window for all time", () => {
    expect(
      dateWindow({ preset: "custom", from: "", to: "2026-10-05" }, NOON).since,
    ).toBeUndefined();
    expect(dateWindow({ preset: "all", from: "", to: "" }, NOON)).toEqual({});
  });
});

describe("buildHistoryParams", () => {
  const context = { mineEmail: "ivan@edu.hse.ru", facetKinds: FACETS };

  it("builds an empty query except for the kinds when no filter is set", () => {
    const params = buildHistoryParams(EMPTY_VCS_FILTERS, context);
    expect(Object.keys(params)).toEqual(["kind"]);
  });

  it("maps mine to the profile e-mail and a person to their e-mail", () => {
    expect(
      buildHistoryParams({ ...EMPTY_VCS_FILTERS, author: AUTHOR_MINE }, context)
        .authorEmail,
    ).toBe("ivan@edu.hse.ru");
    expect(
      buildHistoryParams(
        { ...EMPTY_VCS_FILTERS, author: "anna@edu.hse.ru" },
        context,
      ).authorEmail,
    ).toBe("anna@edu.hse.ru");
    expect(
      buildHistoryParams({ ...EMPTY_VCS_FILTERS, author: AUTHOR_ALL }, context)
        .authorEmail,
    ).toBeUndefined();
  });

  it("ignores mine while the profile is not filled in", () => {
    expect(
      buildHistoryParams(
        { ...EMPTY_VCS_FILTERS, author: AUTHOR_MINE },
        { ...context, mineEmail: null },
      ).authorEmail,
    ).toBeUndefined();
  });

  it("trims the query and passes sync, kinds and the date window", () => {
    const params = buildHistoryParams(
      {
        ...EMPTY_VCS_FILTERS,
        query: "  рисунок ",
        kinds: ["edit"],
        sync: "unpushed",
        preset: "today",
      },
      { ...context, now: NOON },
    );
    expect(params).toMatchObject({
      q: "рисунок",
      kind: ["edit"],
      sync: "unpushed",
    });
    expect(params.since).toBeDefined();
  });
});

describe("commit helpers", () => {
  it("recognises versions that exist only in the repository", () => {
    expect(isIncomingOnly({ sync: "incoming" })).toBe(true);
    expect(isIncomingOnly({ sync: "pushed" })).toBe(false);
    expect(isIncomingOnly({ sync: null })).toBe(false);
    expect(isIncomingOnly({})).toBe(false);
  });

  it("treats a version as own without an e-mail or a profile", () => {
    expect(isOwnCommit({ author_email: "a@x.ru" }, null)).toBe(true);
    expect(isOwnCommit({}, "ivan@x.ru")).toBe(true);
    expect(isOwnCommit({ author_email: "IVAN@x.ru" }, "ivan@x.ru")).toBe(true);
    expect(isOwnCommit({ author_email: "anna@x.ru" }, "ivan@x.ru")).toBe(false);
  });
});
