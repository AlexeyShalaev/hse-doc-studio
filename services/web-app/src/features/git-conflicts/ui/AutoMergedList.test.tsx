import { cleanup, render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { i18n } from "@shared/lib/i18n";
import { AutoMergedList, type AutoMergedItem } from "./AutoMergedList";

const ITEMS: AutoMergedItem[] = [
  { path: "references.bib", action: "merged" },
  { path: "chapters/one.tex", action: "take_theirs" },
  { path: "chapters/two.tex", action: "take_theirs" },
  {
    path: "images/results.png",
    action: "binary_newest",
    copy_path: "images/results.conflict-b71d0e4.png",
  },
  { path: "chapters/old.tex", action: "delete" },
];

const renderList = (
  props: Partial<{
    items: AutoMergedItem[];
    selectedPath: string | null;
    defaultOpen: boolean;
  }> = {},
) => {
  const onSelect = vi.fn();
  render(
    <AutoMergedList
      items={props.items ?? ITEMS}
      selectedPath={props.selectedPath ?? null}
      onSelect={onSelect}
      {...(props.defaultOpen === undefined
        ? {}
        : { defaultOpen: props.defaultOpen })}
    />,
  );
  return onSelect;
};

describe("AutoMergedList", () => {
  beforeEach(async () => {
    await i18n.changeLanguage("ru");
  });
  afterEach(cleanup);

  it("is collapsed and counts the files", () => {
    renderList();
    const toggle = screen.getByRole("button", {
      name: /Решено автоматически · 5/,
    });
    expect(toggle).toHaveAttribute("aria-expanded", "false");
    expect(screen.queryByTitle("references.bib")).toBeNull();
  });

  it("opens on click and says what was done to each file", async () => {
    const user = userEvent.setup();
    const onSelect = renderList();
    await user.click(
      screen.getByRole("button", { name: /Решено автоматически/ }),
    );
    expect(screen.getByText(/Здесь решать нечего/)).toBeInTheDocument();
    expect(screen.getByTestId("auto-summary")).toHaveTextContent(
      "Более новая: 1 · Объединено: 1 · Из репозитория: 2 · Удалён: 1",
    );
    expect(screen.getAllByText("Из репозитория")).toHaveLength(2);
    await user.click(screen.getByTitle("chapters/two.tex"));
    expect(onSelect).toHaveBeenCalledWith("chapters/two.tex");
  });

  it("shows the name of the copy next to a newest-wins picture", async () => {
    const user = userEvent.setup();
    renderList();
    await user.click(
      screen.getByRole("button", { name: /Решено автоматически/ }),
    );
    expect(
      screen.getByText("images/results.conflict-b71d0e4.png"),
    ).toBeInTheDocument();
    expect(screen.getAllByText(/Вторая версия сохранена как/)).toHaveLength(1);
  });

  it("keeps a selected file visible even when collapsed", () => {
    renderList({ selectedPath: "references.bib" });
    expect(
      screen.getByRole("button", { name: /Решено автоматически/ }),
    ).toHaveAttribute("aria-expanded", "true");
    expect(
      screen.getByTitle("references.bib").closest("button"),
    ).toHaveAttribute("aria-current", "true");
  });

  it("can start open", () => {
    renderList({ defaultOpen: true });
    expect(screen.getByTitle("references.bib")).toBeInTheDocument();
  });

  it("renders nothing without files", () => {
    renderList({ items: [] });
    expect(screen.queryByRole("button")).toBeNull();
  });

  it("falls back to the raw action for one it does not know", async () => {
    const user = userEvent.setup();
    renderList({ items: [{ path: "x.txt", action: "teleported" }] });
    await user.click(
      screen.getByRole("button", { name: /Решено автоматически/ }),
    );
    expect(screen.getAllByText("teleported").length).toBeGreaterThan(0);
  });

  it("speaks English", async () => {
    await i18n.changeLanguage("en");
    renderList({ defaultOpen: true });
    expect(
      screen.getByRole("button", { name: /Resolved automatically · 5/ }),
    ).toBeInTheDocument();
    expect(screen.getByTestId("auto-summary")).toHaveTextContent(
      "Newer kept: 1",
    );
  });
});
