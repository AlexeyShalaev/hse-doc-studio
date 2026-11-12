import { afterEach, describe, expect, it } from "vitest";
import { selectionGeometry } from "./pdfSelection";

const box = (left: number, top: number, width: number, height: number) =>
  ({
    left,
    top,
    width,
    height,
    right: left + width,
    bottom: top + height,
    x: left,
    y: top,
    toJSON: () => ({}),
  }) as DOMRect;

const page = (num: number, rect: DOMRect): HTMLElement => {
  const el = document.createElement("div");
  el.dataset.page = String(num);
  el.getBoundingClientRect = () => rect;
  return el;
};

afterEach(() => {
  document.body.replaceChildren();
});

describe("selectionGeometry", () => {
  it("переводит прямоугольники выделения в пункты страницы и сливает куски строки", () => {
    const container = document.createElement("div");
    container.append(
      page(1, box(10, 0, 600, 800)),
      page(2, box(10, 812, 600, 800)),
    );
    document.body.append(container);
    const range = {
      getClientRects: () => [
        box(110, 200, 40, 16),
        box(151, 200, 60, 16),
        box(30, 220, 80, 16),
        box(30, 900, 80, 16),
      ],
    } as unknown as Range;

    const found = selectionGeometry(range, container, 2);

    expect(found?.page).toBe(1);
    expect(found?.rects).toEqual([
      { x: 50, y: 100, width: 50.5, height: 8 },
      { x: 10, y: 110, width: 40, height: 8 },
    ]);
  });

  it("выделение вне страниц ничего не даёт", () => {
    const container = document.createElement("div");
    container.append(page(1, box(10, 0, 600, 800)));
    const range = {
      getClientRects: () => [box(900, 900, 10, 10)],
    } as unknown as Range;

    expect(selectionGeometry(range, container, 1)).toBeNull();
  });
});
