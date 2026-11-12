import { act, render } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { useScrollHint } from "./useScrollHint";

// jsdom не считает раскладку: ширины строки и вкладок задаём сами.
const ROW = { width: 300, scrollWidth: 700 };
const TAB_WIDTH = 100;

const layout = (row: HTMLElement) => {
  let scrollLeft = 0;
  Object.defineProperty(row, "clientWidth", { value: ROW.width });
  Object.defineProperty(row, "scrollWidth", { value: ROW.scrollWidth });
  Object.defineProperty(row, "scrollLeft", {
    get: () => scrollLeft,
    set: (v: number) => {
      scrollLeft = v;
    },
  });
  row.getBoundingClientRect = () => ({ left: 0, right: ROW.width }) as DOMRect;
  Array.from(row.children).forEach((tab, index) => {
    (tab as HTMLElement).getBoundingClientRect = () => {
      const left = index * TAB_WIDTH - scrollLeft;
      return { left, right: left + TAB_WIDTH, width: TAB_WIDTH } as DOMRect;
    };
  });
  const scrollTo = vi.fn((opts: ScrollToOptions) => {
    scrollLeft = opts.left ?? scrollLeft;
    row.dispatchEvent(new Event("scroll"));
  });
  row.scrollTo = scrollTo as unknown as typeof row.scrollTo;
  return scrollTo;
};

const Row = ({ active }: { active: number }) => {
  const ref = useScrollHint(active);
  return (
    <div ref={ref} data-testid="row">
      {Array.from({ length: 7 }, (_, i) => (
        <button key={i} type="button" aria-selected={i === active}>
          {i}
        </button>
      ))}
    </div>
  );
};

describe("useScrollHint", () => {
  afterEach(() => {
    vi.restoreAllMocks();
  });

  it("marks the edges that hide tabs and follows the scroll", () => {
    const { getByTestId, rerender } = render(<Row active={0} />);
    const row = getByTestId("row");
    layout(row);
    // Ширины появились после монтирования: перерисовка с тем же ключом снова считает края.
    rerender(<Row active={1} />);
    expect(row.getAttribute("data-scroll-end")).toBe("true");
    expect(row.hasAttribute("data-scroll-start")).toBe(false);

    act(() => {
      row.scrollLeft = 400;
      row.dispatchEvent(new Event("scroll"));
    });
    expect(row.getAttribute("data-scroll-start")).toBe("true");
    expect(row.hasAttribute("data-scroll-end")).toBe(false);
  });

  it("scrolls the selected tab into view, leaving room for the fade", () => {
    const { getByTestId, rerender } = render(<Row active={0} />);
    const row = getByTestId("row");
    const scrollTo = layout(row);

    // Вкладка 5 (500-600 px) за правым краем: докручиваем так, чтобы справа остался запас 2rem.
    rerender(<Row active={5} />);
    expect(scrollTo).toHaveBeenLastCalledWith({
      left: 600 + 32 - 300,
      behavior: "smooth",
    });
    expect(row.getAttribute("data-scroll-start")).toBe("true");

    // Вкладка 1 (100-200 px) за левым краем: слева тоже запас.
    rerender(<Row active={1} />);
    expect(scrollTo).toHaveBeenLastCalledWith({
      left: 100 - 32,
      behavior: "smooth",
    });

    // Вкладка видна целиком: строка не дёргается.
    scrollTo.mockClear();
    rerender(<Row active={2} />);
    expect(scrollTo).not.toHaveBeenCalled();
  });

  it("does not animate when the user prefers reduced motion", () => {
    vi.spyOn(window, "matchMedia").mockImplementation(
      (query: string) =>
        ({
          matches: query.includes("reduce"),
          media: query,
          addEventListener: () => undefined,
          removeEventListener: () => undefined,
        }) as unknown as MediaQueryList,
    );
    const { getByTestId, rerender } = render(<Row active={0} />);
    const scrollTo = layout(getByTestId("row"));
    rerender(<Row active={6} />);
    expect(scrollTo).toHaveBeenLastCalledWith({
      left: 700 + 32 - 300,
      behavior: "auto",
    });
  });
});
