import { fireEvent, render, screen } from "@testing-library/react";
import type * as pdfjsLib from "pdfjs-dist";
import { describe, expect, it, vi } from "vitest";

vi.mock("pdfjs-dist", () => ({
  GlobalWorkerOptions: {},
  TextLayer: vi.fn(),
}));

import { PdfPage } from "./PdfPage";

// Страница рисуется лениво (по IntersectionObserver), а слой меток сразу: его и проверяем.
const fakePdf = {} as pdfjsLib.PDFDocumentProxy;
const PX_PER_MM = 72 / 25.4;

describe("PdfPage: метки", () => {
  it("рамка места подписи: обводка с подписью вместо картинки", () => {
    render(
      <PdfPage
        pdf={fakePdf}
        dim={{ num: 1, widthPt: 595, heightPt: 842 }}
        scale={1}
        searchQuery=""
        stamps={[
          {
            page: 1,
            src: "ignored.png",
            xMm: 110,
            yMm: 130,
            widthMm: 40,
            heightMm: 22,
            label: "Ваша подпись",
            highlight: true,
          },
          {
            page: 1,
            src: "sig.png",
            xMm: 10,
            yMm: 10,
            widthMm: 30,
            heightMm: 12,
            label: "Студент",
          },
        ]}
      />,
    );
    const frame = screen.getByTestId("pdf-stamp-frame");
    expect(frame).toHaveClass("pdf-stamp-frame");
    expect(frame).toHaveTextContent("Ваша подпись");
    // jsdom 31 сериализует длины с округлением до 6 значащих цифр.
    expect(frame.style.left).toMatch(/px$/);
    expect(parseFloat(frame.style.left)).toBeCloseTo(110 * PX_PER_MM, 3);
    expect(frame.querySelector("img")).toBeNull();
    // Обычная метка рисуется картинкой, как раньше.
    expect(screen.getByAltText("Студент")).toHaveAttribute("src", "sig.png");
  });
});

describe("PdfPage: метки комментариев", () => {
  it("значок на поле страницы открывает тред, у выбранного подсвечен фрагмент", () => {
    const onMarkClick = vi.fn();
    render(
      <PdfPage
        pdf={fakePdf}
        dim={{ num: 1, widthPt: 595, heightPt: 842 }}
        scale={2}
        searchQuery=""
        marks={[
          {
            id: "rvt_1",
            rects: [{ x: 72, y: 120, width: 200, height: 12 }],
            active: true,
            resolved: false,
            title: "Комментарий: Рита",
          },
          {
            id: "rvt_2",
            rects: [{ x: 72, y: 124, width: 50, height: 12 }],
            active: false,
            resolved: false,
            title: "Комментарий: Борис",
          },
        ]}
        onMarkClick={onMarkClick}
      />,
    );

    const first = screen.getByTestId("pdf-review-mark-rvt_1");
    const second = screen.getByTestId("pdf-review-mark-rvt_2");
    // Значки рядом по высоте не накладываются: второй сдвинут влево.
    expect(parseFloat(second.style.left)).toBeLessThan(
      parseFloat(first.style.left),
    );
    const hl = screen.getByTestId("pdf-review-hl-active");
    expect(parseFloat(hl.style.top)).toBe(240);
    expect(parseFloat(hl.style.width)).toBe(400);
    fireEvent.click(second);
    expect(onMarkClick).toHaveBeenCalledWith("rvt_2");
  });
});
