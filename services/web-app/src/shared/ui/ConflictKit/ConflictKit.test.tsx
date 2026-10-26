import { useState } from "react";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";
import {
  ActionTag,
  CountBadges,
  FileList,
  FileRowShell,
  Notice,
  ViewTabs,
  toneColor,
} from ".";

describe("ConflictKit", () => {
  it("maps every tone to a design token", () => {
    expect(toneColor("err")).toBe("var(--c-err)");
    expect(toneColor("warn")).toBe("var(--c-warn)");
    expect(toneColor("ok")).toBe("var(--c-ok)");
    expect(toneColor("info")).toBe("var(--c-info)");
    expect(toneColor("muted")).toBe("var(--fg-2)");
  });

  it("colours an action tag by tone", () => {
    render(<ActionTag label="конфликт" tone="err" />);
    expect(screen.getByText("конфликт")).toHaveStyle({
      color: "var(--c-err)",
      minWidth: "74px",
    });
  });

  describe("FileRowShell", () => {
    it("selects on click and reports the selected row to assistive tech", async () => {
      const user = userEvent.setup();
      const onSelect = vi.fn();
      const { rerender } = render(
        <FileList>
          <FileRowShell
            path="main.tex"
            isSelected={false}
            onSelect={onSelect}
            tag={<ActionTag label="слияние" tone="warn" />}
            trailing={<span>2</span>}
          />
        </FileList>,
      );
      const row = screen.getByRole("button", { name: /main\.tex/ });
      expect(row).not.toHaveAttribute("aria-current");
      await user.click(row);
      expect(onSelect).toHaveBeenCalledTimes(1);
      rerender(
        <FileList>
          <FileRowShell
            path="main.tex"
            isSelected
            onSelect={onSelect}
            tag={<ActionTag label="слияние" tone="warn" />}
          />
        </FileList>,
      );
      expect(screen.getByRole("button", { name: /main\.tex/ })).toHaveAttribute(
        "aria-current",
        "true",
      );
    });

    it("keeps the path readable on hover and the controls outside the row button", () => {
      render(
        <FileRowShell
          path="a/very/long/path/chapter.tex"
          isSelected={false}
          onSelect={() => undefined}
        >
          <button type="button">Моё</button>
        </FileRowShell>,
      );
      expect(screen.getByTitle("a/very/long/path/chapter.tex")).toBeVisible();
      const control = screen.getByRole("button", { name: "Моё" });
      expect(
        screen.getByRole("button", { name: /chapter\.tex/ }),
      ).not.toContainElement(control);
    });

    it("renders no controls row without children", () => {
      const { container } = render(
        <FileRowShell path="x" isSelected={false} onSelect={() => undefined} />,
      );
      expect(container.querySelectorAll("button")).toHaveLength(1);
      expect(container.firstElementChild?.children).toHaveLength(1);
    });
  });

  describe("Notice", () => {
    it("is a passive warning by default", () => {
      render(<Notice text="Проект изменился" />);
      expect(screen.getByText("Проект изменился")).toBeVisible();
      expect(screen.queryByRole("alert")).toBeNull();
    });

    it("can announce an error with an action", async () => {
      const user = userEvent.setup();
      const onRetry = vi.fn();
      render(
        <Notice
          tone="err"
          role="alert"
          text="Ошибка"
          action={
            <button type="button" onClick={onRetry}>
              Повторить
            </button>
          }
        />,
      );
      expect(screen.getByRole("alert")).toHaveTextContent("Ошибка");
      await user.click(screen.getByRole("button", { name: "Повторить" }));
      expect(onRetry).toHaveBeenCalled();
    });

    it("uses a soft background of its tone", () => {
      render(<Notice tone="info" role="status" text="Информация" />);
      expect(screen.getByRole("status").style.background).toBe(
        "var(--c-info-soft)",
      );
    });
  });

  it("renders count badges as «count · label» in the tone colour", () => {
    render(
      <CountBadges
        items={[
          { key: "conflict", count: 3, label: "конфликты", tone: "err" },
          { key: "add", count: 1, label: "новые", tone: "ok" },
        ]}
      />,
    );
    const badge = screen.getByText("3 · конфликты");
    expect(badge).toHaveClass("badge");
    expect(badge).toHaveStyle({ color: "var(--c-err)" });
    expect(screen.getByText("1 · новые")).toHaveStyle({ color: "var(--c-ok)" });
  });

  it("switches views with ViewTabs and highlights the active one", async () => {
    const user = userEvent.setup();
    const Harness = () => {
      const [view, setView] = useState<"mine" | "theirs">("mine");
      return (
        <ViewTabs
          views={[
            { value: "mine", label: "Моё" },
            { value: "theirs", label: "Их" },
          ]}
          value={view}
          onChange={setView}
        />
      );
    };
    render(<Harness />);
    expect(screen.getByRole("button", { name: "Моё" })).toHaveClass("primary");
    await user.click(screen.getByRole("button", { name: "Их" }));
    expect(screen.getByRole("button", { name: "Их" })).toHaveClass("primary");
    expect(screen.getByRole("button", { name: "Моё" })).not.toHaveClass(
      "primary",
    );
  });
});
