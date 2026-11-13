import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, beforeAll, describe, expect, it, vi } from "vitest";
import { DateMarkOverlay } from "./DateMarkOverlay";

// Рамка метки даты на превью (docs/design/signing-route.md, 14.2): тащится и тянется за угол,
// ширина и высота меняются независимо; наверх уходит только итог жеста.

const PLACE = { x_mm: 100, y_mm: 150, width_mm: 20, height_mm: 6 };

const mount = (editable = true) => {
  const onCommit = vi.fn();
  render(
    <div style={{ position: "relative" }}>
      <DateMarkOverlay
        testId="mark"
        place={PLACE}
        text="13"
        align="center"
        label="Дата: 13"
        pageWidthMm={210}
        pageHeightMm={297}
        pxPerMm={2}
        editable={editable}
        onCommit={onCommit}
      />
    </div>,
  );
  return onCommit;
};

beforeAll(() => {
  // jsdom без захвата указателя.
  Element.prototype.setPointerCapture = () => undefined;
  Element.prototype.releasePointerCapture = () => undefined;
});

afterEach(() => {
  cleanup();
});

const pointer = (x: number, y: number) => ({
  pointerId: 1,
  button: 0,
  clientX: x,
  clientY: y,
});

describe("DateMarkOverlay", () => {
  it("перетаскивание двигает рамку в мм, размер тот же", () => {
    const onCommit = mount();
    const frame = screen.getByTestId("mark");
    fireEvent.pointerDown(frame, pointer(0, 0));
    fireEvent.pointerMove(frame, pointer(20, 10));
    fireEvent.pointerUp(frame, pointer(20, 10));
    expect(onCommit).toHaveBeenCalledWith({
      x_mm: 110,
      y_mm: 155,
      width_mm: 20,
      height_mm: 6,
    });
  });

  it("угол тянет ширину и высоту независимо, не меньше 4 × 3 мм", () => {
    const onCommit = mount();
    const frame = screen.getByTestId("mark");
    const handle = frame.lastElementChild as HTMLElement;
    fireEvent.pointerDown(handle, pointer(0, 0));
    fireEvent.pointerMove(frame, pointer(-100, 4));
    fireEvent.pointerUp(frame, pointer(-100, 4));
    expect(onCommit).toHaveBeenCalledWith({
      x_mm: 100,
      y_mm: 150,
      width_mm: 4,
      height_mm: 8,
    });
  });

  it("щелчок без движения ничего не сохраняет", () => {
    const onCommit = mount();
    const frame = screen.getByTestId("mark");
    fireEvent.pointerDown(frame, pointer(5, 5));
    fireEvent.pointerUp(frame, pointer(5, 5));
    expect(onCommit).not.toHaveBeenCalled();
  });

  it("без правки рамка не слушает указатель и угла нет", () => {
    mount(false);
    const frame = screen.getByTestId("mark");
    expect(frame.style.pointerEvents).toBe("none");
    expect(frame.children).toHaveLength(1);
    expect(frame).toHaveAccessibleName("Дата: 13");
  });
});
