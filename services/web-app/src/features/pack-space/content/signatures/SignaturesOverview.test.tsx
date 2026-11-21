import { cleanup, fireEvent, screen } from "@testing-library/react";
import { afterEach, beforeAll, describe, expect, it, vi } from "vitest";
import { packStudioKeys } from "@entities/pack-studio";
import { i18n } from "@shared/lib";
import { loadPackSpaceNamespace } from "@shared/lib/i18n/packSpaceNamespace";
import { GALLERY_REF, GALLERY_WORKSPACE } from "../../galleryKit";
import ContentMain from "../ContentMain";
import { SIGNATURES_PLAIN } from "./fixtures";
import { renderSignatures } from "./signaturesTestKit";

vi.mock("pdfjs-dist", () => ({
  GlobalWorkerOptions: {},
  getDocument: () => ({ promise: Promise.resolve(null) }),
  version: "0",
}));

const PART = "part=signatures";

describe("раздел «Подписи и места»", () => {
  beforeAll(async () => {
    await loadPackSpaceNamespace();
    await i18n.changeLanguage("ru");
  });
  afterEach(cleanup);

  it("какие подписи есть, где стоят, в каких документах: простыми словами", async () => {
    renderSignatures(<ContentMain />, PART);

    expect(await screen.findByTestId("ct-sg-overview")).toBeInTheDocument();
    const author = screen.getByTestId("ct-sgo-author");
    expect(author).toHaveTextContent("Автор");
    expect(author).toHaveTextContent("обязательная");
    expect(author).toHaveTextContent("у каждого автора");
    expect(author).toHaveTextContent("Общее место: страница 1.");
    // У автора своё место в техзадании, у руководителя общее и в техзадании, и в соглашении.
    expect(author).toHaveTextContent("Техническое задание");
    expect(author).toHaveTextContent("своё место");
    expect(screen.getByTestId("ct-sgo-supervisor")).toHaveTextContent(
      "Соглашение о неразглашении",
    );
    expect(screen.getByTestId("ct-sgo-consultant")).toHaveTextContent(
      "по строке в тексте документа",
    );
    const text = screen.getByTestId("ct-sg-overview").textContent;
    expect(text).not.toMatch(/слот|якор|манифест/i);
  });

  it("«Расставить» открывает документ на «Подписи», порядок подписания ведёт в «Сроки и сдачу»", async () => {
    renderSignatures(<ContentMain />, PART);

    fireEvent.click(
      await screen.findByTestId("ct-sgo-go-author-technical_specification"),
    );
    await vi.waitFor(() => {
      const url = screen.getByTestId("location").textContent;
      expect(url).toContain("doc=technical_specification");
      expect(url).toContain("seg=signatures");
      expect(url).not.toContain("part=");
    });
  });

  it("порядок подписания ведёт в «Сроки и сдачу»", async () => {
    renderSignatures(<ContentMain />, PART);
    fireEvent.click(await screen.findByTestId("ct-sgo-order"));
    await vi.waitFor(() => {
      expect(screen.getByTestId("location").textContent).toContain(
        "part=deadlines",
      );
    });
  });

  it("в версии нет подписей: пояснение", async () => {
    renderSignatures(<ContentMain />, PART, {
      before: (client) => {
        client.setQueryData(
          packStudioKeys.signatures(GALLERY_WORKSPACE.id, GALLERY_REF, null),
          { ...SIGNATURES_PLAIN, slots: [] },
        );
      },
    });
    expect(await screen.findByTestId("ct-sgo-empty")).toHaveTextContent(
      "В версии пока нет подписей",
    );
  });
});
