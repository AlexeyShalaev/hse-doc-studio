import { useState } from "react";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it } from "vitest";
import "@shared/lib/i18n";
import { Popover, PopoverClose, PopoverContent, PopoverTrigger } from ".";

const Harness = ({ modal = false }: { modal?: boolean }) => (
  <div>
    <button type="button">outside</button>
    <Popover modal={modal}>
      <PopoverTrigger asChild>
        <button type="button">Open details</button>
      </PopoverTrigger>
      <PopoverContent width={300} aria-label="Sync details">
        <button type="button">first</button>
        <button type="button">second</button>
        <PopoverClose asChild>
          <button type="button">done</button>
        </PopoverClose>
      </PopoverContent>
    </Popover>
  </div>
);

describe("Popover", () => {
  it("is closed until the trigger is activated", async () => {
    const user = userEvent.setup();
    render(<Harness />);
    expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
    const trigger = screen.getByRole("button", { name: "Open details" });
    expect(trigger).toHaveAttribute("aria-expanded", "false");
    await user.click(trigger);
    expect(screen.getByRole("dialog", { name: "Sync details" })).toBeVisible();
    expect(trigger).toHaveAttribute("aria-expanded", "true");
  });

  it("applies the requested width", async () => {
    const user = userEvent.setup();
    render(<Harness />);
    await user.click(screen.getByRole("button", { name: "Open details" }));
    expect(screen.getByRole("dialog")).toHaveStyle({ width: "300px" });
  });

  it("closes on Escape and returns focus to the trigger", async () => {
    const user = userEvent.setup();
    render(<Harness />);
    const trigger = screen.getByRole("button", { name: "Open details" });
    await user.click(trigger);
    await user.keyboard("{Escape}");
    expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
    expect(trigger).toHaveFocus();
  });

  it("closes from inside through PopoverClose", async () => {
    const user = userEvent.setup();
    render(<Harness />);
    await user.click(screen.getByRole("button", { name: "Open details" }));
    await user.click(screen.getByRole("button", { name: "done" }));
    expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
  });

  it("closes on a click outside", async () => {
    const user = userEvent.setup();
    render(<Harness />);
    await user.click(screen.getByRole("button", { name: "Open details" }));
    await user.click(screen.getByRole("button", { name: "outside" }));
    expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
  });

  it("keeps Tab inside the panel when modal", async () => {
    const user = userEvent.setup();
    render(<Harness modal />);
    await user.click(screen.getByRole("button", { name: "Open details" }));
    const dialog = screen.getByRole("dialog");
    for (let i = 0; i < 6; i += 1) {
      await user.tab();
      expect(dialog).toContainElement(document.activeElement as HTMLElement);
    }
  });

  it("can be controlled", async () => {
    const user = userEvent.setup();
    const Controlled = () => {
      const [open, setOpen] = useState(true);
      return (
        <Popover open={open} onOpenChange={setOpen}>
          <PopoverTrigger asChild>
            <button type="button">t</button>
          </PopoverTrigger>
          <PopoverContent aria-label="c">body</PopoverContent>
        </Popover>
      );
    };
    render(<Controlled />);
    expect(screen.getByRole("dialog")).toBeVisible();
    await user.keyboard("{Escape}");
    expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
  });
});
