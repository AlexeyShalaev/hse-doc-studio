import { act, render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import type { ColumnDef } from "@tanstack/react-table";
import { useState, type ReactNode } from "react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { i18n } from "@shared/lib/i18n";
import type { PickerItem, PickerPage } from "../lib/serverList/types";
import { DataTable } from "./DataTable";
import { NoResults } from "./EmptyState";
import { FilterMenu } from "./FilterBar";
import { Pagination } from "./Pagination";
import { Picker, type PickerSource } from "./Picker";
import { SearchInput } from "./SearchInput";

beforeEach(async () => {
  await i18n.changeLanguage("ru");
});

const withQuery = (node: ReactNode) => {
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  });
  return render(
    <QueryClientProvider client={client}>{node}</QueryClientProvider>,
  );
};

describe("Pagination", () => {
  it("пишет диапазон с разделителями тысяч и переходит по номеру", async () => {
    const onPage = vi.fn();
    render(
      <Pagination page={0} pageSize={50} total={12345} onPageChange={onPage} />,
    );
    expect(screen.getByText(/1–50 из 12\s345/)).toBeInTheDocument();
    const jump = screen.getByRole("textbox", { name: /Номер страницы/ });
    await userEvent.clear(jump);
    await userEvent.type(jump, "999{Enter}");
    // За пределами списка: на последнюю страницу.
    expect(onPage).toHaveBeenLastCalledWith(246);
    await userEvent.click(
      screen.getByRole("button", { name: "Последняя страница" }),
    );
    expect(onPage).toHaveBeenLastCalledWith(246);
    expect(
      screen.getByRole("button", { name: "Первая страница" }),
    ).toBeDisabled();
  });

  it("журнал: «Показать ещё» и «из N» только с оценкой", async () => {
    const more = vi.fn();
    const { rerender } = render(
      <Pagination
        mode="cursor"
        shown={50}
        hasMore
        onLoadMore={more}
        totalEstimate={250000}
      />,
    );
    expect(screen.getByText(/Показано 50 из 250\s000/)).toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: "Показать ещё" }));
    expect(more).toHaveBeenCalledTimes(1);
    rerender(
      <Pagination
        mode="cursor"
        shown={21}
        hasMore={false}
        onLoadMore={more}
        totalEstimate={null}
      />,
    );
    expect(screen.getByText("Показана 21 запись")).toBeInTheDocument();
    expect(screen.getByText("Больше записей нет")).toBeInTheDocument();
  });
});

describe("SearchInput", () => {
  it("отдаёт обрезанный поиск после паузы, Esc очищает", async () => {
    vi.useFakeTimers({ shouldAdvanceTime: true });
    const onChange = vi.fn();
    render(<SearchInput value="" onChange={onChange} />);
    const box = screen.getByRole("searchbox", { name: "Поиск" });
    await userEvent.type(box, "  анна ");
    expect(onChange).not.toHaveBeenCalled();
    act(() => {
      vi.advanceTimersByTime(320);
    });
    expect(onChange).toHaveBeenLastCalledWith("анна");
    await userEvent.keyboard("{Escape}");
    expect(box).toHaveValue("");
    expect(onChange).toHaveBeenLastCalledWith("");
    vi.useRealTimers();
  });
});

describe("NoResults и DataTable", () => {
  type Row = { id: string; name: string; email: string };
  const COLS: ColumnDef<Row>[] = [
    { accessorKey: "name", header: "Имя" },
    { accessorKey: "email", header: "Почта" },
  ];

  it("сортирует только разрешённые столбцы", () => {
    render(
      <DataTable
        caption="Люди"
        columns={COLS}
        data={[{ id: "1", name: "Анна", email: "a@x" }]}
        getRowId={(r) => r.id}
        sortable={["name"]}
        onSortingChange={() => undefined}
      />,
    );
    expect(screen.getByRole("button", { name: /Имя/ })).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /Почта/ })).toBeNull();
  });

  it("столбец без accessor сортируется по allowlist, новые первыми", async () => {
    const onSort = vi.fn();
    render(
      <DataTable
        caption="Люди"
        columns={[
          {
            id: "created",
            header: "Создан",
            sortDescFirst: true,
            cell: () => "—",
          },
        ]}
        data={[{ id: "1", name: "Анна", email: "a@x" }]}
        getRowId={(r) => r.id}
        sortable={["created"]}
        sorting={[]}
        onSortingChange={onSort}
      />,
    );
    await userEvent.click(screen.getByRole("button", { name: /Создан/ }));
    expect(onSort).toHaveBeenCalledWith([{ id: "created", desc: true }]);
  });

  it("с фильтрами пустой ответ значит «ничего не найдено»", async () => {
    const reset = vi.fn();
    render(
      <DataTable
        caption="Люди"
        columns={COLS}
        data={[]}
        getRowId={(r) => r.id}
        emptyTitle="Людей пока нет"
        filtered
        searchQuery="zzz"
        onResetFilters={reset}
      />,
    );
    expect(screen.queryByText("Людей пока нет")).toBeNull();
    expect(screen.getByText("Ничего не найдено")).toBeInTheDocument();
    expect(screen.getByText(/«zzz»/)).toBeInTheDocument();
    await userEvent.click(
      screen.getByRole("button", { name: "Сбросить фильтры" }),
    );
    expect(reset).toHaveBeenCalledTimes(1);
  });

  it("NoResults без сброса не рисует кнопку", () => {
    render(<NoResults />);
    expect(screen.queryByRole("button")).toBeNull();
  });
});

describe("FilterMenu", () => {
  it("выбирает несколько значений и показывает числа", async () => {
    const Harness = () => {
      const [values, setValues] = useState<string[]>([]);
      return (
        <FilterMenu
          label="Статус"
          values={values}
          onChange={setValues}
          options={[
            { value: "active", label: "Активные", count: 11800 },
            { value: "disabled", label: "Отключены", count: 54 },
          ]}
        />
      );
    };
    render(<Harness />);
    await userEvent.click(screen.getByRole("button", { name: /Статус/ }));
    const group = screen.getByRole("group", { name: "Статус" });
    expect(within(group).getByText(/11\s800/)).toBeInTheDocument();
    await userEvent.click(
      within(group).getByRole("checkbox", { name: /Активные/ }),
    );
    await userEvent.click(
      within(group).getByRole("checkbox", { name: /Отключены/ }),
    );
    expect(
      within(group).getByRole("checkbox", { name: /Отключены/ }),
    ).toHaveAttribute("aria-checked", "true");
    expect(screen.getByText("2 выбрано")).toBeInTheDocument();
  });
});

describe("Picker", () => {
  const PEOPLE: PickerItem[] = Array.from({ length: 25 }, (_, i) => ({
    kind: "user",
    id: `u${String(i)}`,
    name: `Мария ${String(i)}`,
    detail: `m${String(i)}@example.org`,
  }));

  const source = (search: PickerSource["search"]): PickerSource => ({
    key: ["test", "people"],
    search,
  });

  it("ищет на сервере, листает клавиатурой и просит уточнить", async () => {
    const search = vi.fn(
      (q: string, { limit }: { limit: number }): Promise<PickerPage> => {
        const found = PEOPLE.filter((p) => p.name.includes(q));
        return Promise.resolve({
          items: found.slice(0, limit),
          has_more: found.length > limit,
        });
      },
    );
    const onChange = vi.fn();
    withQuery(
      <Picker
        label="Человек"
        source={source(search)}
        value={null}
        onChange={onChange}
      />,
    );
    await userEvent.click(screen.getByRole("button", { name: "Человек" }));
    expect(await screen.findByText(/Показаны первые 20/)).toBeInTheDocument();
    expect(search).toHaveBeenCalledWith(
      "",
      expect.objectContaining({ limit: 20 }),
    );
    const box = screen.getByRole("combobox", { name: "Человек" });
    await userEvent.type(box, "{ArrowDown}{ArrowDown}");
    expect(screen.getAllByRole("option")[2]).toHaveAttribute(
      "aria-selected",
      "true",
    );
    await userEvent.keyboard("{Enter}");
    expect(onChange).toHaveBeenCalledWith(PEOPLE[2]);
  });

  it("говорит «нет совпадений»", async () => {
    withQuery(
      <Picker
        label="Человек"
        source={source(() => Promise.resolve({ items: [], has_more: false }))}
        value={null}
        onChange={() => undefined}
      />,
    );
    await userEvent.click(screen.getByRole("button", { name: "Человек" }));
    await userEvent.type(
      screen.getByRole("combobox", { name: "Человек" }),
      "zz",
    );
    await waitFor(
      () => {
        expect(screen.getByText("Нет совпадений")).toBeInTheDocument();
      },
      { timeout: 2000 },
    );
  });
});
