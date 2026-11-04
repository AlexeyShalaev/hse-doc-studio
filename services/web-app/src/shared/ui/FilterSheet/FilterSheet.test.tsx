import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";
import "@shared/lib/i18n";
import { FilterSheet, FilterSheetGroup } from ".";

const setup = (activeCount: number, onReset?: () => void) =>
  render(
    <FilterSheet activeCount={activeCount} {...(onReset ? { onReset } : {})}>
      <FilterSheetGroup label="Show">
        <div role="group" aria-label="Show">
          <button type="button">Active</button>
        </div>
      </FilterSheetGroup>
    </FilterSheet>,
  );

describe("FilterSheet", () => {
  it("keeps the filters closed until the button is tapped", async () => {
    setup(0);
    expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
    await userEvent.setup().click(screen.getByTestId("filter-sheet-trigger"));
    const dialog = screen.getByRole("dialog");
    expect(within(dialog).getByText("Show")).toBeVisible();
  });

  it("shows how many filters are on, without a count when none are", () => {
    const { unmount } = setup(0);
    expect(screen.getByTestId("filter-sheet-trigger")).not.toHaveTextContent(
      /\d/,
    );
    unmount();
    setup(2);
    expect(screen.getByTestId("filter-sheet-trigger")).toHaveTextContent("2");
    expect(screen.getByTestId("filter-sheet-trigger")).toHaveAccessibleName(
      /2/,
    );
  });

  it("offers the reset only while something differs from the defaults", async () => {
    const onReset = vi.fn();
    const user = userEvent.setup();
    const { unmount } = setup(0, onReset);
    await user.click(screen.getByTestId("filter-sheet-trigger"));
    expect(screen.queryByTestId("filter-sheet-reset")).not.toBeInTheDocument();
    unmount();
    setup(1, onReset);
    await user.click(screen.getByTestId("filter-sheet-trigger"));
    await user.click(screen.getByTestId("filter-sheet-reset"));
    expect(onReset).toHaveBeenCalledOnce();
  });

  it("closes with the done button", async () => {
    const user = userEvent.setup();
    setup(1);
    await user.click(screen.getByTestId("filter-sheet-trigger"));
    await user.click(screen.getByTestId("filter-sheet-done"));
    expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
  });
});
