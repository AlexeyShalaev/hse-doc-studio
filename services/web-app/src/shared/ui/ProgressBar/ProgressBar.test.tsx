import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it } from "vitest";
import { ProgressBar } from "./ProgressBar";

describe("ProgressBar", () => {
  afterEach(() => {
    cleanup();
  });

  it("сообщает значение скринридеру и ограничивает ширину сотней", () => {
    render(<ProgressBar percent={140} label="Загрузка" />);
    const bar = screen.getByRole("progressbar", { name: "Загрузка" });
    expect(bar).toHaveAttribute("aria-valuenow", "140");
    expect((bar.firstElementChild as HTMLElement).style.width).toBe("100%");
  });

  it("без значения не называет число и показывает бегущую полосу", () => {
    render(<ProgressBar percent={null} label="Загрузка" />);
    const bar = screen.getByRole("progressbar");
    expect(bar).not.toHaveAttribute("aria-valuenow");
    expect(bar.firstElementChild).toHaveClass("animate-pulse");
  });
});
