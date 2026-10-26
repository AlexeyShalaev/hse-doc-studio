import { useState } from "react";
import { cleanup, render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { i18n } from "@shared/lib/i18n";
import { VcsHistoryFilters } from "./VcsHistoryFilters";
import {
  AUTHOR_ALL,
  AUTHOR_MINE,
  EMPTY_VCS_FILTERS,
  type VcsHistoryFilterState,
} from "./vcsHistoryFilters.model";

const KINDS = [
  { kind: "edit", label: "Правки", count: 40 },
  { kind: "sync", label: "Слияния", count: 2 },
  { kind: "other", label: "Другое", count: 5 },
];

const AUTHORS = [
  { value: AUTHOR_ALL, label: "Все авторы" },
  { value: AUTHOR_MINE, label: "Только мои" },
  { value: "anna@edu.hse.ru", label: "Анна Петрова" },
];

const Harness = ({
  initial = EMPTY_VCS_FILTERS,
  onChange,
  showSync = true,
  hasMore = false,
}: {
  initial?: VcsHistoryFilterState;
  onChange?: (state: VcsHistoryFilterState) => void;
  showSync?: boolean;
  hasMore?: boolean;
}) => {
  const [state, setState] = useState(initial);
  return (
    <VcsHistoryFilters
      state={state}
      onChange={(next) => {
        setState(next);
        onChange?.(next);
      }}
      kinds={KINDS}
      authors={AUTHORS}
      showSync={showSync}
      total={47}
      shown={12}
      hasMore={hasMore}
    />
  );
};

describe("VcsHistoryFilters", () => {
  beforeEach(async () => {
    await i18n.changeLanguage("ru");
  });
  afterEach(cleanup);

  it("lets several kind chips be selected and the All chip clears them", async () => {
    const user = userEvent.setup();
    const onChange = vi.fn();
    render(<Harness onChange={onChange} />);
    const group = screen.getByRole("group", { name: "Вид изменения" });
    await user.click(within(group).getByRole("button", { name: /Правки/ }));
    await user.click(within(group).getByRole("button", { name: /Слияния/ }));
    expect(onChange).toHaveBeenLastCalledWith(
      expect.objectContaining({ kinds: ["edit", "sync"] }),
    );
    expect(
      within(group).getByRole("button", { name: /Правки/ }),
    ).toHaveAttribute("aria-pressed", "true");
    expect(within(group).getByRole("button", { name: /^Все/ })).toHaveAttribute(
      "aria-pressed",
      "false",
    );
    await user.click(within(group).getByRole("button", { name: /Правки/ }));
    expect(onChange).toHaveBeenLastCalledWith(
      expect.objectContaining({ kinds: ["sync"] }),
    );
    await user.click(within(group).getByRole("button", { name: /^Все/ }));
    expect(onChange).toHaveBeenLastCalledWith(
      expect.objectContaining({ kinds: [] }),
    );
  });

  it("shows the sync segment only with a connected repository", async () => {
    const user = userEvent.setup();
    const onChange = vi.fn();
    const { rerender } = render(<Harness onChange={onChange} showSync />);
    const group = screen.getByRole("group", { name: "Отправка" });
    expect(within(group).getByRole("button", { name: "Все" })).toHaveAttribute(
      "aria-pressed",
      "true",
    );
    await user.click(
      within(group).getByRole("button", { name: "Не отправлены" }),
    );
    expect(onChange).toHaveBeenLastCalledWith(
      expect.objectContaining({ sync: "unpushed" }),
    );
    await user.click(
      within(group).getByRole("button", { name: "Пришли от коллег" }),
    );
    expect(onChange).toHaveBeenLastCalledWith(
      expect.objectContaining({ sync: "incoming" }),
    );
    rerender(<Harness showSync={false} />);
    expect(screen.queryByRole("group", { name: "Отправка" })).toBeNull();
  });

  it("filters by author through a select that offers mine and teammates", async () => {
    const user = userEvent.setup();
    const onChange = vi.fn();
    render(<Harness onChange={onChange} />);
    const select = screen.getByRole("combobox", { name: "Автор" });
    expect(
      within(select)
        .getAllByRole("option")
        .map((o) => o.textContent),
    ).toEqual(["Все авторы", "Только мои", "Анна Петрова"]);
    await user.selectOptions(select, "Только мои");
    expect(onChange).toHaveBeenLastCalledWith(
      expect.objectContaining({ author: AUTHOR_MINE }),
    );
    await user.selectOptions(select, "Анна Петрова");
    expect(onChange).toHaveBeenLastCalledWith(
      expect.objectContaining({ author: "anna@edu.hse.ru" }),
    );
  });

  it("hides the author select when there is nobody to choose from", () => {
    render(
      <VcsHistoryFilters
        state={EMPTY_VCS_FILTERS}
        onChange={vi.fn()}
        kinds={KINDS}
        authors={[{ value: AUTHOR_ALL, label: "Все авторы" }]}
        showSync={false}
        total={3}
        shown={3}
        hasMore={false}
      />,
    );
    expect(screen.queryByRole("combobox", { name: "Автор" })).toBeNull();
  });

  it("types into the search box and resets everything with one button", async () => {
    const user = userEvent.setup();
    const onChange = vi.fn();
    render(<Harness onChange={onChange} />);
    expect(screen.queryByRole("button", { name: /Сбросить/ })).toBeNull();
    await user.type(
      screen.getByRole("searchbox", { name: "Поиск по изменениям" }),
      "ри",
    );
    expect(onChange).toHaveBeenLastCalledWith(
      expect.objectContaining({ query: "ри" }),
    );
    await user.click(screen.getByRole("button", { name: /Сбросить/ }));
    expect(onChange).toHaveBeenLastCalledWith(EMPTY_VCS_FILTERS);
    expect(screen.queryByRole("button", { name: /Сбросить/ })).toBeNull();
  });

  it("opens the date inputs for a custom range", async () => {
    const user = userEvent.setup();
    render(<Harness />);
    expect(screen.queryByLabelText("Начало периода")).toBeNull();
    await user.selectOptions(
      screen.getByRole("combobox", { name: "Период" }),
      "custom",
    );
    expect(screen.getByLabelText("Начало периода")).toBeInTheDocument();
    expect(screen.getByLabelText("Конец периода")).toBeInTheDocument();
  });

  it("summarises the result: total without filters, found and found-with-more with them", () => {
    render(<Harness />);
    expect(screen.getByText("47 изменений")).toBeInTheDocument();
    cleanup();
    render(<Harness initial={{ ...EMPTY_VCS_FILTERS, query: "рис" }} />);
    expect(screen.getByText("Найдено 12 записей")).toBeInTheDocument();
    cleanup();
    render(
      <Harness initial={{ ...EMPTY_VCS_FILTERS, query: "рис" }} hasMore />,
    );
    expect(
      screen.getByText("Показано 12 записей, есть ещё"),
    ).toBeInTheDocument();
  });

  it("keeps a selected kind chip visible even when it is the only option", () => {
    render(
      <VcsHistoryFilters
        state={{ ...EMPTY_VCS_FILTERS, kinds: ["edit"] }}
        onChange={vi.fn()}
        kinds={[{ kind: "edit", label: "Правки", count: 0 }]}
        authors={[]}
        showSync={false}
        total={0}
        shown={0}
        hasMore={false}
      />,
    );
    expect(screen.getByRole("button", { name: /Правки/ })).toHaveAttribute(
      "aria-pressed",
      "true",
    );
  });

  it("speaks English with the English locale", async () => {
    await i18n.changeLanguage("en");
    render(<Harness />);
    expect(screen.getByRole("group", { name: "Sending" })).toBeInTheDocument();
    expect(screen.getByText("47 changes")).toBeInTheDocument();
    expect(
      screen.getByRole("button", { name: "From colleagues" }),
    ).toBeInTheDocument();
  });
});
