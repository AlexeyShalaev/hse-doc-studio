import { readFileSync } from "node:fs";
import { join } from "node:path";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, beforeAll, describe, expect, it, vi } from "vitest";
import {
  PackSignaturesSchema,
  packStudioApi,
  packStudioKeys,
  type PackSignatures,
} from "@entities/pack-studio";
import type { PdfStampEditorProps } from "@features/signature-stamper";
import { i18n } from "@shared/lib";
import { loadPackStudioNamespace } from "@shared/lib/i18n/packStudioNamespace";
import { PackPlacesEditor } from "./PackPlacesEditor";

vi.mock("pdfjs-dist", () => ({
  GlobalWorkerOptions: {},
  getDocument: () => ({ promise: Promise.resolve(null) }),
  version: "0",
}));

// Холст PDF в jsdom не рисуется: редактор мест подменён кнопками «сдвинуть рамку слота».
vi.mock("@features/signature-stamper", async (importOriginal) => ({
  ...(await importOriginal<Record<string, unknown>>()),
  PdfStampEditor: (props: PdfStampEditorProps) => (
    <div data-testid="stamp-editor" data-readonly={String(props.readOnly)}>
      {props.slotDefs.map((def) => (
        <button
          key={def.id}
          type="button"
          data-testid={`drag-${def.id}`}
          data-muted={String(props.mutedSlots?.has(def.id) ?? false)}
          onClick={() => {
            props.onPlacementChange(def.id, { x_mm: 50, y_mm: 60 });
          }}
        >
          {def.label.ru}
        </button>
      ))}
    </div>
  ),
}));

const REPO = join(import.meta.dirname, "..", "..", "..", "..", "..", "..");
const fixture = (name: string): PackSignatures =>
  PackSignaturesSchema.parse(
    JSON.parse(
      readFileSync(
        join(
          REPO,
          "contracts",
          "pack-studio",
          "fixtures",
          "PackSignatures",
          name,
        ),
        "utf8",
      ),
    ),
  );

const WS = "ws1";
const REF = { pack: "hse-cs-sse", template: "coursework", version: "2026.1.7" };
const BUILD = "0d7f5c2a-3b4e-4f61-8a9b-1c2d3e4f5a6b";

const renderEditor = (data: PackSignatures, onSaved = vi.fn()) => {
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false, staleTime: Infinity } },
  });
  client.setQueryData(packStudioKeys.signatures(WS, REF, BUILD), data);
  // Повторное чтение после правки (фокус окна, сброс кэша) отвечает тем же.
  vi.spyOn(packStudioApi, "signatures").mockResolvedValue(data);
  render(
    <QueryClientProvider client={client}>
      <PackPlacesEditor
        workspaceId={WS}
        versionRef={REF}
        buildId={BUILD}
        pdfUrl="/x.pdf"
        documentLabel="Заявление"
        lang="ru"
        onSaved={onSaved}
      />
    </QueryClientProvider>,
  );
  return { client, onSaved };
};

describe("места подписей пака на PDF предпросмотра", () => {
  beforeAll(async () => {
    await loadPackStudioNamespace();
    await i18n.changeLanguage("ru");
  });
  afterEach(() => {
    cleanup();
    vi.restoreAllMocks();
  });

  it("каталог слотов документа: своё место на строке, место по умолчанию бледное", () => {
    renderEditor(fixture("with_build.json"));

    expect(screen.getByTestId("places-kind-author")).toHaveTextContent(
      "Своё место документа",
    );
    expect(screen.getByTestId("places-binding-author")).toHaveTextContent(
      "По строке author",
    );
    expect(screen.getByTestId("places-kind-supervisor")).toHaveTextContent(
      "Место по умолчанию",
    );
    expect(screen.getByTestId("drag-supervisor")).toHaveAttribute(
      "data-muted",
      "true",
    );
    expect(screen.getByTestId("places-binding-consultant")).toHaveTextContent(
      "нет в этой сборке",
    );
    // Строки даты автора в сборке: метку можно поставить прямо на строку.
    expect(screen.getByTestId("places-line-author.day")).toBeInTheDocument();
  });

  it("перетаскивание пишет место документа с If-Match и сборкой", async () => {
    const data = fixture("with_build.json");
    const patch = vi
      .spyOn(packStudioApi, "patchSignatures")
      .mockResolvedValue({ ...data, etag: '"next"' });
    const { onSaved } = renderEditor(data);

    fireEvent.click(screen.getByTestId("drag-supervisor"));

    await vi.waitFor(() => {
      expect(onSaved).toHaveBeenCalledWith(data.path);
    });
    expect(patch).toHaveBeenCalledWith(
      WS,
      REF,
      {
        build_id: BUILD,
        ops: [
          {
            op: "set_place",
            slot: "supervisor",
            doc: "application",
            box: { page: 1, x_mm: 50, y_mm: 60, width_mm: 40 },
          },
        ],
      },
      data.etag,
    );
  });

  it("действия каталога: сделать местом по умолчанию, метка на строку", async () => {
    const data = fixture("with_build.json");
    const patch = vi
      .spyOn(packStudioApi, "patchSignatures")
      .mockResolvedValue(data);
    renderEditor(data);

    fireEvent.click(screen.getByTestId("places-default-author"));
    await vi.waitFor(() => {
      expect(patch).toHaveBeenCalledTimes(1);
    });
    fireEvent.click(screen.getByTestId("places-line-author.day"));
    await vi.waitFor(() => {
      expect(patch).toHaveBeenCalledTimes(2);
    });

    expect(patch.mock.calls.map((call) => call[2].ops[0])).toEqual([
      { op: "make_default", slot: "author", doc: "application" },
      {
        op: "add_date",
        slot: "author",
        doc: "application",
        anchor: "author.day",
      },
    ]);
  });

  it("отказ сервера виден с причиной", async () => {
    const data = fixture("with_build.json");
    const { ApiError } = await import("@shared/api");
    vi.spyOn(packStudioApi, "patchSignatures").mockRejectedValue(
      new ApiError("x", "place_invalid", 400, {
        reason: "slot 'consultant' does not apply to document 'report'",
      }),
    );
    renderEditor(data);

    fireEvent.click(screen.getByTestId("drag-supervisor"));

    expect(await screen.findByTestId("places-save-error")).toHaveTextContent(
      "does not apply",
    );
  });

  it("выпущенная версия только для просмотра", () => {
    const released = {
      ...fixture("with_build.json"),
      read_only: "version_released" as const,
    };
    renderEditor(released);

    expect(screen.getByTestId("places-read-only")).toBeInTheDocument();
    expect(screen.getByTestId("stamp-editor")).toHaveAttribute(
      "data-readonly",
      "true",
    );
    expect(screen.queryByTestId("places-default-author")).toBeNull();
    expect(screen.queryByTestId("places-line-author.day")).toBeNull();
  });
});
