import { render, screen, within } from "@testing-library/react";
import { beforeEach, describe, expect, it } from "vitest";
import { i18n } from "@shared/lib/i18n";
import { Stepper, type StepperStep } from ".";

const URL_STEP: StepperStep = { id: "url", label: "Адрес" };
const ACCESS_STEP: StepperStep = { id: "access", label: "Доступ" };
const STEPS: StepperStep[] = [
  URL_STEP,
  ACCESS_STEP,
  { id: "check", label: "Проверка" },
];

describe("Stepper", () => {
  beforeEach(async () => {
    await i18n.changeLanguage("ru");
  });

  it("marks only the current step with aria-current=step", () => {
    render(<Stepper steps={STEPS} current="access" label="Подключение" />);
    const list = screen.getByRole("list", { name: "Подключение" });
    const items = within(list).getAllByRole("listitem");
    expect(items).toHaveLength(3);
    expect(items.map((li) => li.getAttribute("aria-current"))).toEqual([
      null,
      "step",
      null,
    ]);
  });

  it("derives done, current and upcoming from the current id", () => {
    render(<Stepper steps={STEPS} current="access" />);
    const states = screen
      .getAllByRole("listitem")
      .map((li) => li.getAttribute("data-state"));
    expect(states).toEqual(["done", "current", "upcoming"]);
  });

  it("spells the state out for assistive technology", () => {
    render(<Stepper steps={STEPS} current="access" />);
    const [done, current, upcoming] = screen.getAllByRole("listitem");
    expect(done).toHaveTextContent("Адрес — выполнено");
    expect(current).toHaveTextContent("Доступ — текущий шаг");
    expect(upcoming).toHaveTextContent("Проверка — впереди");
  });

  it("lets a step override its derived state (failed phase)", () => {
    render(
      <Stepper
        steps={[URL_STEP, { ...ACCESS_STEP, state: "error" }]}
        current="url"
      />,
    );
    const [, second] = screen.getAllByRole("listitem");
    expect(second).toHaveAttribute("data-state", "error");
    expect(second).toHaveTextContent("ошибка");
  });

  it("shows a spinner on the current step while busy", () => {
    const { rerender } = render(<Stepper steps={STEPS} current="url" />);
    expect(screen.queryByRole("status", { hidden: true })).toBeNull();
    rerender(<Stepper steps={STEPS} current="url" busy />);
    expect(screen.getByRole("status", { hidden: true })).toBeInTheDocument();
  });

  it("renders descriptions and meta in the vertical layout only", () => {
    const steps: StepperStep[] = [
      { id: "a", label: "Получаем", description: "из origin", meta: "42%" },
      { id: "b", label: "Отправляем" },
    ];
    const { rerender } = render(
      <Stepper steps={steps} current="a" orientation="vertical" />,
    );
    expect(screen.getByText("из origin")).toBeVisible();
    expect(screen.getByText("42%")).toBeVisible();
    rerender(<Stepper steps={steps} current="a" />);
    expect(screen.queryByText("42%")).toBeNull();
  });

  it("falls back to the first step for an unknown current id", () => {
    render(<Stepper steps={STEPS} current="nope" />);
    expect(screen.getAllByRole("listitem")[0]).toHaveAttribute(
      "aria-current",
      "step",
    );
  });
});
