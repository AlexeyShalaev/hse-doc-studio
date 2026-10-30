import { act, renderHook } from "@testing-library/react";
import type { ReactNode } from "react";
import { MemoryRouter, useLocation } from "react-router";
import { describe, expect, it } from "vitest";
import { mergeHead } from "./useCursorList";
import { dayBoundaryIso, useListQueryState } from "./useListQueryState";

const wrapper =
  (url: string) =>
  ({ children }: { children: ReactNode }) => (
    <MemoryRouter initialEntries={[url]}>{children}</MemoryRouter>
  );

const OPTIONS = {
  filters: {
    status: { multi: true, values: ["active", "disabled"] },
    org: {},
  },
  sort: { fields: ["name", "created_at"], default: "-created_at" },
} as const;

const useHarness = () => {
  const state = useListQueryState({
    filters: OPTIONS.filters,
    sort: { fields: OPTIONS.sort.fields, default: OPTIONS.sort.default },
  });
  return { state, location: useLocation() };
};

describe("useListQueryState", () => {
  it("читает адрес и отбрасывает чужие значения", () => {
    const { result } = renderHook(useHarness, {
      wrapper: wrapper(
        "/admin/users?q=%20анна%20&status=active&status=root&sort=name&page=3&size=100",
      ),
    });
    const s = result.current.state;
    expect(s.q).toBe("анна");
    expect(s.filters.status).toEqual(["active"]);
    expect(s.sort).toEqual({ field: "name", desc: false });
    expect(s.page).toBe(2);
    expect(s.pageSize).toBe(100);
    expect(s.params).toEqual({
      limit: 100,
      offset: 200,
      q: "анна",
      sort: "name",
      status: ["active"],
    });
    expect(s.isFiltered).toBe(true);
  });

  it("searchOnly есть, только когда кроме поиска условий нет", () => {
    const only = renderHook(useHarness, { wrapper: wrapper("/x?q=петр") });
    const both = renderHook(useHarness, {
      wrapper: wrapper("/x?q=петр&status=active"),
    });
    expect(only.result.current.state.searchOnly).toBe("петр");
    expect(both.result.current.state.searchOnly).toBe("");
    expect(both.result.current.state.isFiltered).toBe(true);
  });

  it("перевёрнутый период из адреса меняется местами", () => {
    const { result } = renderHook(
      () =>
        useListQueryState({
          filters: { from: { date: "from" }, to: { date: "to" } },
        }),
      { wrapper: wrapper("/x?from=2026-10-30&to=2026-10-01") },
    );
    expect(result.current.filters.from).toEqual(["2026-10-01"]);
    expect(result.current.filters.to).toEqual(["2026-10-30"]);
    expect(result.current.params.from).toBe(
      dayBoundaryIso("2026-10-01", "from"),
    );
  });

  it("неизвестная сортировка и размер дают значения по умолчанию", () => {
    const { result } = renderHook(useHarness, {
      wrapper: wrapper("/x?sort=password&size=7"),
    });
    expect(result.current.state.sort).toEqual({
      field: "created_at",
      desc: true,
    });
    expect(result.current.state.pageSize).toBe(50);
  });

  it("смена поиска, фильтра и сортировки сбрасывает страницу", () => {
    const { result } = renderHook(useHarness, {
      wrapper: wrapper("/x?page=4"),
    });
    act(() => {
      result.current.state.setFilter("status", ["disabled", "active"]);
    });
    expect(result.current.state.page).toBe(0);
    expect(result.current.location.search).toBe(
      "?status=disabled&status=active",
    );
    act(() => {
      result.current.state.setPage(2);
    });
    expect(result.current.location.search).toContain("page=3");
    act(() => {
      result.current.state.setQ("  мария ");
    });
    expect(result.current.state.q).toBe("мария");
    expect(result.current.state.page).toBe(0);
    act(() => {
      result.current.state.onSortingChange([{ id: "name", desc: true }]);
    });
    expect(result.current.state.params.sort).toBe("-name");
    // Порядок по умолчанию в адрес не пишется.
    act(() => {
      result.current.state.setSort({ field: "created_at", desc: true });
    });
    expect(result.current.location.search).not.toContain("sort=");
    act(() => {
      result.current.state.reset();
    });
    expect(result.current.location.search).toBe("");
  });

  it("дни периода уходят границами ISO с зоной", () => {
    const { result } = renderHook(
      () =>
        useListQueryState({
          mode: "cursor",
          filters: { from: { date: "from" }, to: { date: "to" } },
        }),
      { wrapper: wrapper("/audit?from=2026-10-01&to=2026-10-03&page=5") },
    );
    expect(result.current.params).toEqual({
      limit: 50,
      from: dayBoundaryIso("2026-10-01", "from"),
      to: dayBoundaryIso("2026-10-03", "to"),
    });
    // В режиме курсора страниц нет.
    expect(result.current.page).toBe(0);
    expect(
      Date.parse(dayBoundaryIso("2026-10-03", "to")) -
        Date.parse(dayBoundaryIso("2026-10-03", "from")),
    ).toBeGreaterThanOrEqual(23 * 3_600_000);
  });

  it("приставка разводит два списка на одной странице", () => {
    const { result } = renderHook(() => useListQueryState({ prefix: "m." }), {
      wrapper: wrapper("/x?q=a&m.q=b"),
    });
    expect(result.current.q).toBe("b");
  });
});

describe("mergeHead", () => {
  const page = (ids: string[], next: string | null) => ({
    items: ids.map((id) => ({ id })),
    next_cursor: next,
    total_estimate: null,
  });
  const id = (row: { id: string }) => row.id;

  it("вклеивает свежую голову над загруженными страницами", () => {
    const old = {
      pages: [page(["9", "8", "7"], "c7"), page(["6", "5", "4"], "c4")],
      pageParams: [null, "c7"],
    };
    const merged = mergeHead(old, page(["11", "10", "9"], "c9"), id);
    expect(merged.pages.flatMap((p) => p.items.map(id))).toEqual([
      "11",
      "10",
      "9",
      "8",
      "7",
      "6",
      "5",
      "4",
    ]);
    expect(merged.pages.at(-1)?.next_cursor).toBe("c4");
  });

  it("без стыка начинает с первой страницы", () => {
    const old = {
      pages: [page(["3", "2"], "c2"), page(["1"], null)],
      pageParams: [null, "c2"],
    };
    const merged = mergeHead(old, page(["9", "8"], "c8"), id);
    expect(merged.pages).toHaveLength(1);
  });
});
