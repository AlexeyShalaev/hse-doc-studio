import { act, render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { useState } from "react";
import type { ColumnDef, SortingState } from "@tanstack/react-table";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { i18n } from "@shared/lib/i18n";
import { ConfirmByName } from "./ConfirmByName";
import { DataTable } from "./DataTable";
import { FilterBar } from "./FilterBar";
import { SecretOnce } from "./SecretOnce";
import { StatusDot } from "./StatusDot";
import { MemoryRouter } from "react-router";
import { ActionMenu } from "./ActionMenu";
import { PageHeader, PageTabs } from "./AdminPage";
import { Badge } from "./Badge";
import { EmptyState, ErrorState } from "./EmptyState";
import { KpiTile } from "./KpiTile";
import { PersonCell } from "./PersonCell";
import { Section, SettingRow } from "./Section";
import { StickySaveBar } from "./StickySaveBar";

type Row = { id: string; name: string };
const COLS: ColumnDef<Row>[] = [
  { accessorKey: "name", header: "Имя" },
  { accessorKey: "id", header: "ID", enableSorting: false },
];
const ROWS: Row[] = [
  { id: "1", name: "Анна" },
  { id: "2", name: "Борис" },
];

beforeEach(async () => {
  await i18n.changeLanguage("ru");
});

describe("DataTable", () => {
  it("exposes table, column headers and sort state", async () => {
    const onSort = vi.fn<(s: SortingState) => void>();
    render(
      <DataTable
        caption="Люди"
        columns={COLS}
        data={ROWS}
        getRowId={(r) => r.id}
        onSortingChange={onSort}
      />,
    );
    const table = screen.getByRole("table", { name: "Люди" });
    expect(within(table).getAllByRole("columnheader")).toHaveLength(2);
    expect(screen.getByRole("columnheader", { name: /Имя/ })).toHaveAttribute(
      "aria-sort",
      "none",
    );
    await userEvent.click(screen.getByRole("button", { name: /Имя/ }));
    expect(onSort).toHaveBeenCalledWith([{ id: "name", desc: false }]);
    // Столбец без сортировки не получает кнопку.
    expect(screen.queryByRole("button", { name: /ID/ })).toBeNull();
  });

  it("marks the sorted column", () => {
    render(
      <DataTable
        caption="Люди"
        columns={COLS}
        data={ROWS}
        getRowId={(r) => r.id}
        sorting={[{ id: "name", desc: true }]}
        onSortingChange={() => undefined}
      />,
    );
    expect(screen.getByRole("columnheader", { name: /Имя/ })).toHaveAttribute(
      "aria-sort",
      "descending",
    );
  });

  it("pages through the server pagination", async () => {
    const onPage = vi.fn();
    render(
      <DataTable
        caption="Люди"
        columns={COLS}
        data={ROWS}
        getRowId={(r) => r.id}
        pagination={{ page: 1, pageSize: 2, total: 5, onPageChange: onPage }}
      />,
    );
    expect(screen.getByText("3–4 из 5")).toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: /Вперёд/ }));
    await userEvent.click(screen.getByRole("button", { name: /Назад/ }));
    expect(onPage).toHaveBeenNthCalledWith(1, 2);
    expect(onPage).toHaveBeenNthCalledWith(2, 0);
  });

  it("disables paging at the edges", () => {
    render(
      <DataTable
        caption="Люди"
        columns={COLS}
        data={ROWS}
        getRowId={(r) => r.id}
        pagination={{
          page: 1,
          pageSize: 2,
          total: 4,
          onPageChange: () => undefined,
        }}
      />,
    );
    expect(screen.getByRole("button", { name: /Назад/ })).toBeEnabled();
    expect(screen.getByRole("button", { name: /Вперёд/ })).toBeDisabled();
  });

  it("hides paging while one page holds everything", () => {
    render(
      <DataTable
        caption="Люди"
        columns={COLS}
        data={ROWS}
        getRowId={(r) => r.id}
        pagination={{
          page: 0,
          pageSize: 2,
          total: 2,
          onPageChange: () => undefined,
        }}
      />,
    );
    expect(screen.queryByRole("button", { name: /Назад/ })).toBeNull();
  });

  it("shows the empty state with its action", () => {
    render(
      <DataTable
        caption="Люди"
        columns={COLS}
        data={[]}
        getRowId={(r) => r.id}
        emptyTitle="Нет людей"
        emptyAction={<button type="button">Добавить</button>}
      />,
    );
    expect(screen.getByText("Нет людей")).toBeInTheDocument();
    expect(
      screen.getByRole("button", { name: "Добавить" }),
    ).toBeInTheDocument();
  });

  it("shows the error and retries", async () => {
    const onRetry = vi.fn();
    render(
      <DataTable
        caption="Люди"
        columns={COLS}
        data={[]}
        getRowId={(r) => r.id}
        error="Сбой"
        onRetry={onRetry}
      />,
    );
    expect(screen.getByRole("alert")).toHaveTextContent("Сбой");
    await userEvent.click(screen.getByRole("button", { name: "Повторить" }));
    expect(onRetry).toHaveBeenCalledTimes(1);
  });

  it("shows skeleton rows while loading", () => {
    render(
      <DataTable
        caption="Люди"
        columns={COLS}
        data={[]}
        getRowId={(r) => r.id}
        loading
        skeletonRows={3}
      />,
    );
    expect(screen.getByRole("table")).toHaveAttribute("aria-busy", "true");
    expect(screen.queryByText("Здесь пока пусто")).toBeNull();
  });

  it("selects a row by click and keyboard", async () => {
    const onRow = vi.fn();
    render(
      <DataTable
        caption="Люди"
        columns={COLS}
        data={ROWS}
        getRowId={(r) => r.id}
        onRowClick={onRow}
      />,
    );
    const row = screen.getByText("Анна").closest("tr");
    expect(row).not.toBeNull();
    row?.focus();
    await userEvent.keyboard("{Enter}");
    await userEvent.click(screen.getByText("Борис"));
    expect(onRow).toHaveBeenCalledTimes(2);
  });
});

describe("ConfirmByName", () => {
  const setup = (onConfirm = vi.fn()) => {
    render(
      <ConfirmByName
        isOpen
        onClose={() => undefined}
        onConfirm={onConfirm}
        name="hse-cs"
        title="Удалить"
        confirmLabel="Удалить навсегда"
      />,
    );
    return onConfirm;
  };

  it("enables the button only on an exact match", async () => {
    const onConfirm = setup();
    const button = screen.getByRole("button", { name: "Удалить навсегда" });
    expect(button).toBeDisabled();
    const input = screen.getByRole("textbox");
    await userEvent.type(input, "HSE-cs");
    expect(button).toBeDisabled();
    await userEvent.clear(input);
    await userEvent.type(input, "hse-cs");
    expect(button).toBeEnabled();
    await userEvent.click(button);
    expect(onConfirm).toHaveBeenCalledTimes(1);
  });

  it("does not match a name with extra spaces", async () => {
    setup();
    await userEvent.type(screen.getByRole("textbox"), "hse-cs ");
    expect(
      screen.getByRole("button", { name: "Удалить навсегда" }),
    ).toBeDisabled();
  });
});

describe("SecretOnce", () => {
  it("asks for confirmation when closing before copying", async () => {
    const onClose = vi.fn();
    render(<SecretOnce label="Токен" value="rt_secret" onClose={onClose} />);
    await userEvent.click(screen.getByRole("button", { name: "Готово" }));
    expect(onClose).not.toHaveBeenCalled();
    expect(screen.getByRole("alert")).toBeInTheDocument();
    await userEvent.click(
      screen.getByRole("button", { name: "Закрыть без копирования" }),
    );
    expect(onClose).toHaveBeenCalledTimes(1);
  });

  it("closes at once after copying", async () => {
    const onClose = vi.fn();
    const user = userEvent.setup();
    render(<SecretOnce label="Токен" value="rt_secret" onClose={onClose} />);
    await user.click(screen.getByRole("button", { name: /Копировать|Copy/ }));
    await user.click(screen.getByRole("button", { name: "Готово" }));
    expect(onClose).toHaveBeenCalledTimes(1);
  });
});

describe("FilterBar", () => {
  it("debounces search and toggles filters", async () => {
    vi.useFakeTimers({ shouldAdvanceTime: true });
    const onSearch = vi.fn();
    const onFilter = vi.fn();
    const Host = () => {
      const [v, setV] = useState("");
      return (
        <FilterBar
          search=""
          onSearchChange={onSearch}
          filters={[
            {
              id: "s",
              label: "Статус",
              value: v,
              onChange: (x) => {
                setV(x);
                onFilter(x);
              },
              options: [{ value: "a", label: "Активные" }],
            },
          ]}
        />
      );
    };
    render(<Host />);
    const user = userEvent.setup({ advanceTimers: vi.advanceTimersByTime });
    await user.type(screen.getByRole("searchbox"), "ан");
    expect(onSearch).not.toHaveBeenCalled();
    await act(async () => {
      await vi.advanceTimersByTimeAsync(350);
    });
    expect(onSearch).toHaveBeenCalledWith("ан");
    await user.click(screen.getByRole("button", { name: "Активные" }));
    expect(onFilter).toHaveBeenCalledWith("a");
    expect(screen.getByRole("button", { name: "Активные" })).toHaveAttribute(
      "aria-pressed",
      "true",
    );
    vi.useRealTimers();
  });
});

describe("StatusDot", () => {
  it("always carries a text label and a distinct shape", () => {
    const { container } = render(
      <>
        <StatusDot status="online" />
        <StatusDot status="degraded" />
      </>,
    );
    expect(screen.getByText("На связи")).toBeInTheDocument();
    expect(screen.getByText("Работает с ошибками")).toBeInTheDocument();
    expect(container.querySelectorAll("circle").length).toBe(1);
    expect(container.querySelectorAll("path").length).toBe(1);
  });

  it("names the icon when the label is hidden", () => {
    render(<StatusDot status="paused" hideLabel />);
    expect(screen.getByRole("img", { name: "На паузе" })).toBeInTheDocument();
  });
});

describe("StatusDot tones", () => {
  it("labels generic tones in sans text", () => {
    render(
      <>
        <StatusDot status="success" />
        <StatusDot status="danger" />
      </>,
    );
    expect(screen.getByText("В норме")).toBeInTheDocument();
    expect(screen.getByText("Сбой")).toBeInTheDocument();
  });
});

describe("Badge", () => {
  it("is set in sans, not monospace", () => {
    render(<Badge>Администратор</Badge>);
    expect(screen.getByText("Администратор")).toHaveClass("chip", "sans");
  });
});

describe("PageHeader and PageTabs", () => {
  const Tabs = ({ onChange }: { onChange: (id: string) => void }) => {
    const [value, setValue] = useState("a");
    return (
      <PageHeader
        title="Раннеры"
        description="Машины для сборок."
        actions={<button type="button">Создать</button>}
        tabs={
          <PageTabs
            label="Вид"
            value={value}
            onChange={(id) => {
              setValue(id);
              onChange(id);
            }}
            tabs={[
              { id: "a", label: "Раннеры", count: 5, testId: "tab-a" },
              { id: "b", label: "Очередь", testId: "tab-b" },
            ]}
          />
        }
      />
    );
  };

  it("puts the title first and tabs under it, arrows move between tabs", async () => {
    const user = userEvent.setup();
    const onChange = vi.fn();
    render(<Tabs onChange={onChange} />);
    expect(
      screen.getByRole("heading", { level: 1, name: "Раннеры" }),
    ).toBeInTheDocument();
    const tabA = screen.getByTestId("tab-a");
    expect(tabA).toHaveAttribute("aria-selected", "true");
    expect(within(tabA).getByText("5")).toBeInTheDocument();
    tabA.focus();
    await user.keyboard("{ArrowRight}");
    expect(onChange).toHaveBeenLastCalledWith("b");
    expect(screen.getByTestId("tab-b")).toHaveFocus();
  });
});

describe("Section and SettingRow", () => {
  it("links the label to the control and marks env-locked values", () => {
    render(
      <Section title="Почта" description="Отправка писем.">
        <SettingRow label="Сервер" htmlFor="host" locked testId="row">
          <input id="host" />
        </SettingRow>
      </Section>,
    );
    expect(screen.getByRole("region", { name: "Почта" })).toBeInTheDocument();
    expect(screen.getByLabelText(/Сервер/)).toHaveAttribute("id", "host");
    expect(screen.getByTestId("row-locked")).toHaveAccessibleName(
      "Задано в окружении сервера, поменять можно только там.",
    );
  });
});

describe("StickySaveBar", () => {
  it("is hidden without changes and counts them with plural forms", async () => {
    const user = userEvent.setup();
    const onSave = vi.fn();
    const onDiscard = vi.fn();
    const { rerender } = render(
      <StickySaveBar dirtyCount={0} onSave={onSave} onDiscard={onDiscard} />,
    );
    expect(screen.queryByTestId("save-bar")).toBeNull();
    rerender(
      <StickySaveBar dirtyCount={3} onSave={onSave} onDiscard={onDiscard} />,
    );
    expect(screen.getByText("3 несохранённых изменения")).toBeInTheDocument();
    await user.click(screen.getByTestId("save-bar-save"));
    await user.click(screen.getByTestId("save-bar-discard"));
    expect(onSave).toHaveBeenCalledOnce();
    expect(onDiscard).toHaveBeenCalledOnce();
    rerender(
      <StickySaveBar
        dirtyCount={1}
        busy
        onSave={onSave}
        onDiscard={onDiscard}
      />,
    );
    expect(screen.getByTestId("save-bar-save")).toBeDisabled();
    expect(screen.getByText("1 несохранённое изменение")).toBeInTheDocument();
  });
});

describe("KpiTile", () => {
  it("links to its section and shows loading and error states", () => {
    render(
      <MemoryRouter>
        <KpiTile label="Люди" value="6" to="/admin/users" testId="k1" />
        <KpiTile label="Место" value="" loading testId="k2" />
        <KpiTile label="Сервисы" value="" error="Не удалось" testId="k3" />
      </MemoryRouter>,
    );
    expect(screen.getByTestId("k1")).toHaveAttribute("href", "/admin/users");
    expect(within(screen.getByTestId("k2")).getByRole("status")).toBeTruthy();
    expect(
      within(screen.getByTestId("k3")).getByRole("alert"),
    ).toHaveTextContent("Не удалось");
  });
});

describe("PersonCell", () => {
  it("shows name and email, and a neutral fallback instead of a raw id", () => {
    render(
      <>
        <PersonCell id="u_1" name="Мария Келлер" email="maria@example.org" />
        <PersonCell id="u_01hx7k9zz" />
      </>,
    );
    expect(screen.getByText("Мария Келлер")).toBeInTheDocument();
    expect(screen.getByText("maria@example.org")).toBeInTheDocument();
    expect(screen.getByText("Неизвестный пользователь")).toBeInTheDocument();
    expect(screen.queryByText("u_01hx7k9zz")).toBeNull();
  });
});

describe("EmptyState and ErrorState", () => {
  it("offers the main action and a retry", async () => {
    const user = userEvent.setup();
    const onRetry = vi.fn();
    render(
      <>
        <EmptyState
          title="Токенов пока нет"
          action={<button type="button">Создать токен</button>}
        />
        <ErrorState onRetry={onRetry} />
      </>,
    );
    expect(screen.getByText("Токенов пока нет")).toBeInTheDocument();
    expect(screen.getByRole("alert")).toHaveTextContent(
      "Не удалось загрузить данные",
    );
    await user.click(screen.getByRole("button", { name: "Повторить" }));
    expect(onRetry).toHaveBeenCalledOnce();
  });
});

describe("ActionMenu", () => {
  it("opens from the ⋯ button and runs the chosen action", async () => {
    const user = userEvent.setup();
    const onPause = vi.fn();
    render(
      <ActionMenu
        label="Действия с runner-1"
        items={[
          { id: "pause", label: "Пауза", onSelect: onPause },
          { id: "rm", label: "Удалить", danger: true, onSelect: vi.fn() },
        ]}
      />,
    );
    await user.click(
      screen.getByRole("button", { name: "Действия с runner-1" }),
    );
    expect(
      await screen.findByRole("menuitem", { name: "Удалить" }),
    ).toHaveAttribute("data-danger", "true");
    await user.click(screen.getByRole("menuitem", { name: "Пауза" }));
    expect(onPause).toHaveBeenCalledOnce();
  });
});
