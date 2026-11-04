import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import type { ColumnDef } from "@tanstack/react-table";
import { afterEach, describe, expect, it, vi } from "vitest";
import "@shared/lib/i18n";
import { installViewport } from "@shared/lib/viewport/testing";
import { DataTable } from ".";

type Row = { id: string; name: string; role: string; logins: number };

const rows: Row[] = [
  { id: "1", name: "Anna", role: "owner", logins: 7 },
  { id: "2", name: "Boris", role: "editor", logins: 2 },
];

const columns: ColumnDef<Row>[] = [
  { id: "name", header: "Person", cell: ({ row }) => row.original.name },
  { id: "role", header: "Role", cell: ({ row }) => row.original.role },
  {
    id: "logins",
    header: "Logins",
    cell: ({ row }) => row.original.logins,
    meta: { card: "hidden" },
  },
  {
    id: "actions",
    header: () => <span className="sr-only">Actions</span>,
    cell: ({ row }) => (
      <button type="button" aria-label={`Actions for ${row.original.name}`}>
        ...
      </button>
    ),
  },
];

const renderTable = (
  props: Partial<Parameters<typeof DataTable<Row>>[0]> = {},
) =>
  render(
    <DataTable<Row>
      caption="People"
      columns={columns}
      data={rows}
      getRowId={(row) => row.id}
      {...props}
    />,
  );

describe("DataTable on a phone", () => {
  let viewport: ReturnType<typeof installViewport> | undefined;
  afterEach(() => {
    viewport?.restore();
    viewport = undefined;
  });

  it("stays a table on a desktop", () => {
    viewport = installViewport(1360);
    renderTable();
    expect(screen.getByRole("table", { name: "People" })).toBeVisible();
    expect(screen.queryAllByRole("listitem")).toHaveLength(0);
  });

  it("turns rows into cards with a title, labelled lines and the actions in the corner", () => {
    viewport = installViewport(390);
    renderTable();
    expect(screen.queryByRole("table")).not.toBeInTheDocument();
    const cards = screen.getAllByRole("listitem");
    expect(cards).toHaveLength(2);
    const first = within(cards[0]!);
    expect(first.getByText("Anna")).toBeVisible();
    expect(first.getByText("Role")).toBeVisible();
    expect(first.getByText("owner")).toBeVisible();
    expect(
      first.getByRole("button", { name: "Actions for Anna" }),
    ).toBeVisible();
  });

  it("leaves out the columns marked hidden", () => {
    viewport = installViewport(360);
    renderTable();
    expect(screen.queryByText("Logins")).not.toBeInTheDocument();
    expect(screen.queryByText("7")).not.toBeInTheDocument();
  });

  it("opens the row from the card but not from its action button", async () => {
    viewport = installViewport(390);
    const onRowClick = vi.fn();
    renderTable({ onRowClick });
    const user = userEvent.setup();
    await user.click(screen.getByRole("button", { name: "Actions for Boris" }));
    expect(onRowClick).not.toHaveBeenCalled();
    await user.click(screen.getByText("Boris"));
    expect(onRowClick).toHaveBeenCalledWith(rows[1]);
  });

  it("can keep the table on a phone", () => {
    viewport = installViewport(390);
    renderTable({ phone: "table" });
    expect(screen.getByRole("table")).toBeVisible();
  });

  it("shows the empty state in place of cards", () => {
    viewport = installViewport(390);
    renderTable({ data: [], emptyTitle: "Nobody here" });
    expect(screen.getByText("Nobody here")).toBeVisible();
  });
});
