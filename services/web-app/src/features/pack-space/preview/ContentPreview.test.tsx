import { cleanup, fireEvent, screen } from "@testing-library/react";
import {
  afterEach,
  beforeAll,
  beforeEach,
  describe,
  expect,
  it,
  vi,
} from "vitest";
import { packStudioApi, resetPackFilesRevision } from "@entities/pack-studio";
import { i18n } from "@shared/lib";
import { loadPackSpaceNamespace } from "@shared/lib/i18n/packSpaceNamespace";
import { loadPackStudioNamespace } from "@shared/lib/i18n/packStudioNamespace";
import { CONTENT_TEXT_PATH, CONTENT_VERSION_DIR } from "../content/fixtures";
import { takePendingReveal } from "../content/text/revealLine";
import ContentPreview from "./ContentPreview";
import { previewBuild } from "./fixtures";
import { finding, renderPreview, withLint } from "./previewTestKit";

vi.mock("@shared/ui", async () => ({
  ...(await vi.importActual<Record<string, unknown>>("@shared/ui")),
  PdfViewer: ({ url }: { url: string }) => (
    <div data-testid="pdf-viewer" data-url={url} />
  ),
}));

const location = () => screen.getByTestId("location").textContent;

const FINDINGS = [
  finding(9, "warning", "Поле project.purpose не заполнено."),
  finding(6, "error", "Нет поля name_shrt. Возможно, name_short."),
  finding(
    2,
    "warning",
    "Чужой файл.",
    `${CONTENT_VERSION_DIR}/files/other.tex`,
  ),
];

describe("предпросмотр в «Содержимом»", () => {
  beforeAll(async () => {
    await loadPackSpaceNamespace();
    await loadPackStudioNamespace();
    await i18n.changeLanguage("ru");
  });
  beforeEach(() => {
    window.localStorage.clear();
    resetPackFilesRevision();
    vi.spyOn(packStudioApi, "startPreview").mockResolvedValue([
      previewBuild("succeeded"),
    ]);
  });
  afterEach(() => {
    cleanup();
    vi.restoreAllMocks();
  });

  it("показывает документ, открытый слева, и собирает его сам", async () => {
    renderPreview(<ContentPreview />, "doc=technical_specification&seg=text");

    expect(await screen.findByTestId("sp-pv-page")).toBeInTheDocument();
    expect(screen.getByTestId("sp-preview")).toHaveAttribute(
      "data-doc",
      "technical_specification",
    );
    expect(screen.getByTestId("sp-preview")).toHaveTextContent(
      "Техническое задание",
    );
  });

  it("замечания к файлу: число и порядок (ошибка раньше), чужого файла нет", async () => {
    renderPreview(<ContentPreview />, "doc=technical_specification&seg=text", {
      before: withLint(FINDINGS),
    });

    expect(await screen.findByTestId("sp-pv-findings-count")).toHaveTextContent(
      "2",
    );
    const rows = screen.getAllByTestId("sp-pv-find");
    expect(rows[0]).toHaveTextContent("Строка 6");
    expect(rows[0]).toHaveAttribute("data-severity", "error");
    expect(rows[1]).toHaveTextContent("Строка 9");
    expect(screen.queryByText("Чужой файл.")).toBeNull();
  });

  it("без замечаний: так и сказано", async () => {
    renderPreview(<ContentPreview />, "doc=technical_specification&seg=text", {
      before: withLint([]),
    });
    expect(await screen.findByTestId("sp-pv-findings-none")).toHaveTextContent(
      "Замечаний к этому файлу нет.",
    );
  });

  it("«Строка N» просит редактор показать строку; в «Тексте» адрес не меняется", async () => {
    renderPreview(<ContentPreview />, "doc=technical_specification&seg=text", {
      before: withLint(FINDINGS),
    });
    fireEvent.click((await screen.findAllByTestId("sp-pv-line")).at(0)!);

    expect(location()).toContain("seg=text");
    expect(takePendingReveal(CONTENT_TEXT_PATH)).toMatchObject({ line: 6 });
  });

  it("из «Условий» «Строка N» открывает «Текст» этого файла", async () => {
    renderPreview(<ContentPreview />, "doc=technical_specification&seg=terms", {
      before: withLint(FINDINGS),
    });
    fireEvent.click((await screen.findAllByTestId("sp-pv-line")).at(1)!);

    expect(location()).not.toContain("seg=terms");
    expect(location()).toContain("file=");
    expect(takePendingReveal(CONTENT_TEXT_PATH)).toMatchObject({ line: 9 });
  });

  it("у раздела формы страницы нет: пояснение вместо панели", async () => {
    renderPreview(<ContentPreview />, "part=fields");

    expect(await screen.findByTestId("sp-pv-none")).toHaveTextContent(
      "Выберите документ",
    );
    expect(screen.queryByTestId("sp-preview")).toBeNull();
  });

  it("без адреса открыт последний или первый документ: предпросмотр его же", async () => {
    renderPreview(<ContentPreview />);
    expect(await screen.findByTestId("sp-preview")).toHaveAttribute(
      "data-doc",
      "technical_specification",
    );
  });
});
