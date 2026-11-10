import { render, screen } from "@testing-library/react";
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
