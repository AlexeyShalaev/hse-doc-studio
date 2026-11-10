import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { i18n } from "@shared/lib";
import { installViewport } from "@shared/lib/viewport/testing";

// Документ не грузится: проверяем только панель инструментов.
vi.mock("pdfjs-dist", () => ({
  GlobalWorkerOptions: {},
  getDocument: () => ({
    promise: new Promise(() => undefined),
    destroy: () => Promise.resolve(),
  }),
  version: "0",
}));

import { PdfViewer } from "./PdfViewer";

const MARGINS = { leftMm: 30, rightMm: 15, topMm: 20, bottomMm: 20 };

const renderViewer = () =>
  render(
    <PdfViewer
      url="/api/v1/projects/p1/files/doc.pdf"
      marginGuideMm={MARGINS}
      toolbarExtras={<button type="button">PDF</button>}
    />,
  );

describe("PdfViewer: панель инструментов", () => {
  let viewport: ReturnType<typeof installViewport> | undefined;
  beforeEach(async () => {
    await i18n.changeLanguage("en");
    // Телефон открывает документ по ширине: подгонка следит за размером окна.
    vi.stubGlobal(
      "ResizeObserver",
      class {
        observe = vi.fn();
        unobserve = vi.fn();
        disconnect = vi.fn();
      },
    );
  });
  afterEach(() => {
    vi.unstubAllGlobals();
    viewport?.restore();
    viewport = undefined;
  });

  it("на десктопе все инструменты на панели, меню «Ещё» нет", () => {
    viewport = installViewport(1280);
    renderViewer();
    for (const name of [
      "Outline",
      "Thumbnails",
      "GOST margins",
      "Ruler",
      "Night mode",
      "Print",
    ]) {
      expect(screen.getByRole("button", { name })).toBeInTheDocument();
    }
    expect(
      screen.getByRole("textbox", { name: "Search the PDF" }),
    ).toBeVisible();
    expect(screen.queryByTestId("pdf-toolbar-more")).not.toBeInTheDocument();
  });

  it("на телефоне вторичные инструменты в меню «Ещё», страницы и масштаб на панели", async () => {
    viewport = installViewport(390);
    renderViewer();
    expect(screen.getByRole("button", { name: "Zoom out" })).toBeVisible();
    expect(
      screen.getByRole("textbox", { name: "Page number" }),
    ).toBeInTheDocument();
    for (const name of ["Thumbnails", "Ruler", "Night mode", "Print"]) {
      expect(screen.queryByRole("button", { name })).not.toBeInTheDocument();
    }
    expect(
      screen.queryByRole("textbox", { name: "Search the PDF" }),
    ).not.toBeInTheDocument();
    expect(screen.getByRole("button", { name: "PDF" })).toBeVisible();

    const user = userEvent.setup();
    await user.click(screen.getByTestId("pdf-toolbar-more"));
    const items = screen
      .getAllByRole("menuitemcheckbox")
      .map((el) => [el.textContent, el.getAttribute("aria-checked")]);
    expect(items).toEqual([
      ["Outline", "false"],
      ["Thumbnails", "false"],
      ["Search the PDF", "false"],
      ["GOST margins", "false"],
      ["Ruler", "false"],
      ["Night mode", "false"],
    ]);
    expect(screen.getByRole("menuitem", { name: "Print" })).toBeVisible();

    await user.click(screen.getByRole("menuitemcheckbox", { name: "Ruler" }));
    await user.click(screen.getByTestId("pdf-toolbar-more"));
    expect(
      screen.getByRole("menuitemcheckbox", { name: "Ruler" }),
    ).toHaveAttribute("aria-checked", "true");
  });

  it("на телефоне поиск открывается строкой из меню и закрывается крестиком", async () => {
    viewport = installViewport(390);
    renderViewer();
    const user = userEvent.setup();
    await user.click(screen.getByTestId("pdf-toolbar-more"));
    await user.click(
      screen.getByRole("menuitemcheckbox", { name: "Search the PDF" }),
    );
    const input = screen.getByRole("textbox", { name: "Search the PDF" });
    await waitFor(() => {
      expect(input).toHaveFocus();
    });
    await user.type(input, "intro");
    await user.click(screen.getByRole("button", { name: "Close search" }));
    expect(
      screen.queryByRole("textbox", { name: "Search the PDF" }),
    ).not.toBeInTheDocument();
  });
});
