import { cleanup, fireEvent, screen, waitFor } from "@testing-library/react";
import {
  afterEach,
  beforeAll,
  beforeEach,
  describe,
  expect,
  it,
  vi,
  type MockInstance,
} from "vitest";
import {
  packOutcomeApi,
  packStudioApi,
  resetPackFilesRevision,
} from "@entities/pack-studio";
import { i18n } from "@shared/lib";
import { loadPackSpaceNamespace } from "@shared/lib/i18n/packSpaceNamespace";
import { loadPackStudioNamespace } from "@shared/lib/i18n/packStudioNamespace";
import DetailsPanel from "../details/DetailsPanel";
import { PV_DOC, previewBuild } from "./fixtures";
import { renderPreview } from "./previewTestKit";

vi.mock("@shared/ui", async () => ({
  ...(await vi.importActual<Record<string, unknown>>("@shared/ui")),
  PdfViewer: ({ url }: { url: string }) => (
    <div data-testid="pdf-viewer" data-url={url} />
  ),
}));

const location = () => screen.getByTestId("location").textContent;
const SEL = `sel=documents%3A${PV_DOC}`;

describe("предпросмотр в «Подробностях» «Результата»", () => {
  let start: MockInstance<typeof packStudioApi.startPreview>;
  beforeAll(async () => {
    await loadPackSpaceNamespace();
    await loadPackStudioNamespace();
    await i18n.changeLanguage("ru");
  });
  beforeEach(() => {
    window.localStorage.clear();
    resetPackFilesRevision();
    start = vi
      .spyOn(packStudioApi, "startPreview")
      .mockResolvedValue([previewBuild("succeeded")]);
    vi.spyOn(packOutcomeApi, "explain").mockRejectedValue(new Error("offline"));
  });
  afterEach(() => {
    cleanup();
    vi.restoreAllMocks();
  });

  it("по кнопке «PDF» в строке (sel и preview=1) панель открывает предпросмотр выбранного документа", async () => {
    renderPreview(<DetailsPanel />, `${SEL}&preview=1`, { tab: "result" });

    expect(await screen.findByTestId("sp-preview")).toHaveAttribute(
      "data-doc",
      PV_DOC,
    );
    expect(await screen.findByTestId("sp-pv-page")).toBeInTheDocument();
    expect(start).toHaveBeenCalledTimes(1);
    // Замечания к файлу относятся к «Содержимому»: здесь списка нет.
    expect(screen.queryByTestId("sp-pv-findings")).toBeNull();
  });

  it("без preview=1 предпросмотра нет и ничего не собирается; кнопка открывает и скрывает его", async () => {
    renderPreview(<DetailsPanel />, SEL, { tab: "result" });

    const toggle = await screen.findByTestId("sp-preview-toggle");
    expect(toggle).toHaveTextContent("Предпросмотр PDF");
    expect(screen.queryByTestId("sp-preview")).toBeNull();
    expect(start).not.toHaveBeenCalled();

    fireEvent.click(toggle);
    expect(location()).toContain("preview=1");
    expect(await screen.findByTestId("sp-preview")).toBeInTheDocument();
    expect(screen.getByTestId("sp-preview-toggle")).toHaveTextContent(
      "Скрыть предпросмотр",
    );

    fireEvent.click(screen.getByTestId("sp-preview-toggle"));
    await waitFor(() => {
      expect(screen.queryByTestId("sp-preview")).toBeNull();
    });
    expect(location()).not.toContain("preview=1");
  });
});
