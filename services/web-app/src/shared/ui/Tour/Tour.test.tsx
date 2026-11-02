import { cleanup, render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";
import { placePopover, spotlightRect } from "./placement";
import { TourOverlay, type TourOverlayLabels } from "./TourOverlay";

const VIEW = { width: 1200, height: 800 };
const BOX = { width: 300, height: 160 };

describe("размещение подсказки", () => {
  it("снизу, если влезает", () => {
    const spot = { top: 100, left: 500, width: 100, height: 40 };
    expect(placePopover(spot, BOX, VIEW).placement).toBe("bottom");
  });

  it("сверху у нижнего края", () => {
    const spot = { top: 700, left: 500, width: 100, height: 40 };
    expect(placePopover(spot, BOX, VIEW).placement).toBe("top");
  });

  it("сбоку у высокого элемента", () => {
    const spot = { top: 10, left: 20, width: 200, height: 780 };
    expect(placePopover(spot, BOX, VIEW).placement).toBe("right");
  });

  it("без элемента по центру, в узком окне шторкой", () => {
    expect(placePopover(null, BOX, VIEW).placement).toBe("center");
    expect(placePopover(null, BOX, { width: 400, height: 700 }).placement).toBe(
      "sheet",
    );
  });

  it("подсказка не выходит за окно", () => {
    const spot = { top: 100, left: 1150, width: 40, height: 30 };
    const box = placePopover(spot, BOX, VIEW);
    expect(box.left + BOX.width).toBeLessThanOrEqual(VIEW.width);
    expect(box.left).toBeGreaterThanOrEqual(0);
  });

  it("подсветка обрезается по окну", () => {
    expect(
      spotlightRect({ top: -20, left: 0, width: 50, height: 40 }, VIEW),
    ).toEqual({ top: 0, left: 0, width: 56, height: 26 });
  });
});

const LABELS: TourOverlayLabels = {
  next: "Далее",
  back: "Назад",
  skip: "Пропустить",
  finish: "Готово",
  progress: "Шаг 2 из 3",
  close: "Закрыть",
};

const renderOverlay = (target?: string) => {
  const handlers = { onNext: vi.fn(), onBack: vi.fn(), onSkip: vi.fn() };
  render(
    <TourOverlay
      stepId="s"
      target={target}
      title="Заголовок"
      body="Текст"
      index={1}
      total={3}
      labels={LABELS}
      {...handlers}
    />,
  );
  return handlers;
};

describe("TourOverlay", () => {
  afterEach(() => {
    cleanup();
    document.body.innerHTML = "";
  });

  it("клавиатура: вправо дальше, влево назад, Esc пропуск", async () => {
    const user = userEvent.setup();
    const h = renderOverlay();
    await user.keyboard("{ArrowRight}");
    await user.keyboard("{ArrowLeft}");
    await user.keyboard("{Escape}");
    expect(h.onNext).toHaveBeenCalledTimes(1);
    expect(h.onBack).toHaveBeenCalledTimes(1);
    expect(h.onSkip).toHaveBeenCalledTimes(1);
  });

  it("нет элемента: подсказка без подсветки, фокус на главной кнопке", () => {
    renderOverlay('[data-tour="missing"]');
    expect(screen.queryByTestId("tour-spotlight")).toBeNull();
    expect(screen.getByRole("dialog")).toHaveTextContent("Заголовок");
    expect(screen.getByTestId("tour-next")).toHaveFocus();
    expect(screen.getByRole("progressbar")).toHaveAttribute(
      "aria-valuenow",
      "2",
    );
  });

  it("элемент найден: есть подсветка", () => {
    const el = document.createElement("button");
    el.dataset.tour = "here";
    el.getBoundingClientRect = () =>
      ({
        top: 10,
        left: 10,
        width: 80,
        height: 30,
        bottom: 40,
        right: 90,
      }) as DOMRect;
    document.body.appendChild(el);
    renderOverlay('[data-tour="here"]');
    expect(screen.getByTestId("tour-spotlight")).toBeInTheDocument();
  });
});
