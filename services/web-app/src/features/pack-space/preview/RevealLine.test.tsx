import { cleanup, fireEvent, screen, waitFor } from "@testing-library/react";
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
import ContentMain from "../content/ContentMain";
import ContentPreview from "./ContentPreview";
import { previewBuild } from "./fixtures";
import { finding, renderPreview, withLint } from "./previewTestKit";

// «Строка N» справа показывает строку в редакторе слева: оба на одном экране «Содержимого».
vi.mock("@shared/ui/CodeEditor", async () => {
  const { createElement } = await import("react");
  return {
    CodeEditor: ({
      value,
      reveal,
    }: {
      value: string;
      reveal?: { line: number };
    }) =>
      createElement("textarea", {
        "data-testid": "code",
        "data-reveal": reveal ? String(reveal.line) : undefined,
        value,
        readOnly: true,
      }),
  };
});
vi.mock("@shared/ui", async () => ({
  ...(await vi.importActual<Record<string, unknown>>("@shared/ui")),
  PdfViewer: () => <div data-testid="pdf-viewer" />,
}));

describe("переход к строке из предпросмотра", () => {
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

  it("список замечаний справа прокручивает редактор слева к строке", async () => {
    renderPreview(
      <>
        <ContentMain />
        <ContentPreview />
      </>,
      "doc=technical_specification&seg=text",
      {
        before: withLint([finding(6, "error", "Нет поля name_shrt.")]),
      },
    );
    expect(await screen.findByTestId("code")).toBeInTheDocument();
    expect(screen.getByTestId("code")).not.toHaveAttribute("data-reveal");
    fireEvent.click((await screen.findAllByTestId("sp-pv-line")).at(0)!);
    await waitFor(() => {
      expect(screen.getByTestId("code")).toHaveAttribute("data-reveal");
    });
  });
});
