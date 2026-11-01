import { render, renderHook, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { i18n } from "@shared/lib/i18n";
import { needsPager } from "../../lib/serverList";
import { isoDay, useDateRangeLabel } from "./DateRangeFilter";
import { SortMenu } from "./SortMenu";

beforeEach(async () => {
  await i18n.changeLanguage("ru");
});

const OPTIONS = [
  { field: "created_at", label: "Дата добавления", descFirst: true },
  { field: "name", label: "Название" },
] as const;

describe("SortMenu", () => {
  it("новое поле в своём направлении, направление меняется отдельно", async () => {
    const onChange = vi.fn();
    render(
      <SortMenu
        options={OPTIONS}
        value={{ field: "name", desc: false }}
        onChange={onChange}
        testId="sort"
      />,
    );
    expect(screen.getByTestId("sort")).toHaveTextContent("Сортировка:Название");
    await userEvent.click(screen.getByTestId("sort"));
    await userEvent.click(
      screen.getByRole("radio", { name: "Дата добавления" }),
    );
    expect(onChange).toHaveBeenLastCalledWith({
      field: "created_at",
      desc: true,
    });
    await userEvent.click(screen.getByRole("radio", { name: "По убыванию" }));
    expect(onChange).toHaveBeenLastCalledWith({ field: "name", desc: true });
    // Выбранное поле повторно ничего не меняет: снять сортировку нельзя.
    onChange.mockClear();
    await userEvent.click(screen.getByRole("radio", { name: "Название" }));
    expect(onChange).not.toHaveBeenCalled();
  });
});

describe("подписи и листание коротких списков", () => {
  it("период словами, как на кнопке фильтра", () => {
    const today = isoDay(new Date());
    const week = new Date();
    week.setDate(week.getDate() - 6);
    const { result } = renderHook(() =>
      useDateRangeLabel({ from: isoDay(week), to: today }),
    );
    expect(result.current).toBe("7 дней");
    const none = renderHook(() => useDateRangeLabel({ from: null, to: null }));
    expect(none.result.current).toBeNull();
  });

  it("строка листания не нужна, пока всё помещается на страницу", () => {
    const state = { page: 0, pageSizes: [25, 50, 100] };
    expect(needsPager(3, state)).toBe(false);
    expect(needsPager(26, state)).toBe(true);
    expect(needsPager(0, { ...state, page: 2 })).toBe(true);
  });
});
