import { cleanup, fireEvent, screen, within } from "@testing-library/react";
import { afterEach, beforeAll, describe, expect, it, vi } from "vitest";
import { packStudioApi, packStudioKeys } from "@entities/pack-studio";
import type { PdfStampEditorProps } from "@features/signature-stamper";
import { ApiError } from "@shared/api";
import { i18n } from "@shared/lib";
import { loadPackSpaceNamespace } from "@shared/lib/i18n/packSpaceNamespace";
import { GALLERY_WORKSPACE } from "../../galleryKit";
import ContentMain from "../ContentMain";
import {
  SIGNATURES_BUILD_ID,
  SIGNATURES_BUILT,
  SIGNATURES_DOC,
  SIGNATURES_PREVIEW_OPTIONS,
  SIGNATURES_RELEASED,
  signaturesBuild,
} from "./fixtures";
import { mockCopyCreated } from "../contentTestKit";
import { seedDocumentBuild } from "./buildSeed";
import { renderSignatures } from "./signaturesTestKit";

vi.mock("pdfjs-dist", () => ({
  GlobalWorkerOptions: {},
  getDocument: () => ({ promise: Promise.resolve(null) }),
  version: "0",
}));

// Холст PDF в jsdom не рисуется: редактор мест подменён кнопками «сдвинуть рамку подписи».
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

const WS = GALLERY_WORKSPACE.id;
const DOC = `doc=${SIGNATURES_DOC}&seg=signatures`;

describe("«Подписи» документа", () => {
  beforeAll(async () => {
    await loadPackSpaceNamespace();
    await i18n.changeLanguage("ru");
  });
  afterEach(() => {
    cleanup();
    vi.restoreAllMocks();
  });

  it("подписи документа словами: своё место, общее, места в PDF нет; чужая подпись только в списке", async () => {
    renderSignatures(<ContentMain />, DOC);

    expect(await screen.findByTestId("places-author")).toHaveAttribute(
      "data-status",
      "own",
    );
    expect(screen.getByTestId("places-author-status")).toHaveTextContent(
      "Стоит на странице 1. Это место только для этого документа.",
    );
    expect(screen.getByTestId("places-author-follow")).toHaveTextContent(
      "Следует за текстом",
    );
    expect(screen.getByTestId("places-supervisor")).toHaveAttribute(
      "data-status",
      "shared",
    );
    expect(screen.getByTestId("places-supervisor")).toHaveTextContent(
      "общее место",
    );
    expect(screen.getByTestId("places-consultant-status")).toHaveTextContent(
      "В этом PDF подписи не видно",
    );
    expect(screen.queryByTestId("places-customer")).toBeNull();
    expect(screen.getByTestId("ct-sg-others")).toHaveTextContent(
      "Подписей версии, которых нет в этом документе: 1",
    );
    // Рамка общего места бледная, своя нет.
    expect(screen.getByTestId("drag-supervisor")).toHaveAttribute(
      "data-muted",
      "true",
    );
    expect(screen.getByTestId("drag-author")).toHaveAttribute(
      "data-muted",
      "false",
    );
  });

  it("слов «слот» и «якорь» на экране нет", async () => {
    renderSignatures(<ContentMain />, DOC);
    await screen.findByTestId("ct-sg");
    const text = screen.getByTestId("ct-signatures").textContent;
    expect(text).not.toMatch(/слот|якор|манифест/i);
  });

  it("перетаскивание пишет место документа со сборкой и If-Match", async () => {
    const patch = vi
      .spyOn(packStudioApi, "patchSignatures")
      .mockResolvedValue({ ...SIGNATURES_BUILT, etag: '"next"' });
    renderSignatures(<ContentMain />, DOC);

    fireEvent.click(await screen.findByTestId("drag-supervisor"));

    await vi.waitFor(() => {
      expect(patch).toHaveBeenCalledTimes(1);
    });
    expect(patch).toHaveBeenCalledWith(
      WS,
      expect.objectContaining({ version: "2026.1.3" }),
      {
        build_id: SIGNATURES_BUILD_ID,
        ops: [
          {
            op: "set_place",
            slot: "supervisor",
            doc: SIGNATURES_DOC,
            box: { page: 1, x_mm: 50, y_mm: 60, width_mm: 40 },
          },
        ],
      },
      SIGNATURES_BUILT.etag,
    );
  });

  it("кнопки карточки: общим местом, вернуть общее, не следовать за текстом, следовать, дата на строку", async () => {
    const patch = vi
      .spyOn(packStudioApi, "patchSignatures")
      .mockResolvedValue(SIGNATURES_BUILT);
    renderSignatures(<ContentMain />, DOC);
    await screen.findByTestId("ct-sg");

    fireEvent.click(screen.getByTestId("places-author-shared"));
    await vi.waitFor(() => {
      expect(patch).toHaveBeenCalledTimes(1);
    });
    fireEvent.click(screen.getByTestId("places-author-useshared"));
    await vi.waitFor(() => {
      expect(patch).toHaveBeenCalledTimes(2);
    });
    fireEvent.click(screen.getByTestId("places-author-follow-off"));
    await vi.waitFor(() => {
      expect(patch).toHaveBeenCalledTimes(3);
    });
    fireEvent.click(screen.getByTestId("places-supervisor-follow-on"));
    await vi.waitFor(() => {
      expect(patch).toHaveBeenCalledTimes(4);
    });
    fireEvent.click(screen.getByTestId("places-line-author.day"));
    await vi.waitFor(() => {
      expect(patch).toHaveBeenCalledTimes(5);
    });

    expect(patch.mock.calls.map((call) => call[2].ops[0])).toEqual([
      { op: "make_default", slot: "author", doc: SIGNATURES_DOC },
      { op: "remove_place", slot: "author", doc: SIGNATURES_DOC },
      { op: "unbind_anchor", slot: "author", doc: SIGNATURES_DOC },
      { op: "bind_anchor", slot: "supervisor", doc: SIGNATURES_DOC },
      {
        op: "add_date",
        slot: "author",
        doc: SIGNATURES_DOC,
        anchor: "author.day",
      },
    ]);
  });

  it("отказ сервера виден с причиной", async () => {
    vi.spyOn(packStudioApi, "patchSignatures").mockRejectedValue(
      new ApiError("x", "place_invalid", 400, { reason: "bad box" }),
    );
    renderSignatures(<ContentMain />, DOC);

    fireEvent.click(await screen.findByTestId("drag-supervisor"));

    expect(await screen.findByTestId("ct-sg-save-error")).toHaveTextContent(
      "bad box",
    );
  });

  it("выпущенная версия: только чтение, действий нет, «Править копию» создаёт копию", async () => {
    renderSignatures(<ContentMain />, DOC, {
      released: true,
      seed: { data: SIGNATURES_RELEASED },
    });

    const lock = await screen.findByTestId("ct-sg-readonly");
    expect(lock).toHaveTextContent("нужна копия версии");
    expect(screen.getByTestId("stamp-editor")).toHaveAttribute(
      "data-readonly",
      "true",
    );
    expect(screen.queryByTestId("places-author-shared")).toBeNull();
    expect(screen.queryByTestId("places-line-author.day")).toBeNull();

    const created = mockCopyCreated("2026.1.3");
    fireEvent.click(within(lock).getByTestId("ct-sg-copy"));
    await vi.waitFor(() => {
      expect(screen.getByTestId("location").textContent).toContain(
        "/2026.1.3/",
      );
    });
    expect(created).toHaveBeenCalledOnce();
    expect(screen.getByTestId("location").textContent).not.toContain("copy=1");
  });

  it("подписей у документа нет: короткое пояснение и ссылка на раздел, PDF не собирается", async () => {
    const start = vi.spyOn(packStudioApi, "startPreview");
    renderSignatures(<ContentMain />, "doc=source_listing&seg=signatures");

    const empty = await screen.findByTestId("ct-sg-none");
    expect(empty).toHaveTextContent("В этом документе подписей нет");
    fireEvent.click(within(empty).getByRole("link"));
    await vi.waitFor(() => {
      expect(screen.getByTestId("location").textContent).toContain(
        "part=signatures",
      );
    });
    expect(start).not.toHaveBeenCalled();
  });

  it("PDF собирается сам при открытии: идёт сборка, затем редактор", async () => {
    const build = { ...SIGNATURES_PREVIEW_OPTIONS };
    const running = signaturesBuild("running");
    const started = vi
      .spyOn(packStudioApi, "startPreview")
      .mockResolvedValue([running]);
    vi.spyOn(packStudioApi, "previewBuild").mockResolvedValue(running);
    renderSignatures(<ContentMain />, DOC, {
      before: (client) => {
        // Без подложенной сборки: экран запускает её сам.
        seedDocumentBuild(
          WS,
          { pack: "hse-cs-sse", template: "coursework", version: "2026.1.3" },
          SIGNATURES_DOC,
          null,
        );
        client.removeQueries({
          queryKey: packStudioKeys.previewBuild(WS, SIGNATURES_BUILD_ID),
        });
        client.setQueryData(
          packStudioKeys.previewOptions(WS, {
            pack: "hse-cs-sse",
            template: "coursework",
            version: "2026.1.3",
          }),
          build,
        );
      },
    });

    expect(await screen.findByTestId("ct-sg-building")).toHaveTextContent(
      "Собираем PDF",
    );
    await vi.waitFor(() => {
      expect(started).toHaveBeenCalledTimes(1);
    });
    expect(started.mock.calls[0]?.[2]).toEqual({
      documents: [SIGNATURES_DOC],
      example: "typical",
      combination: {},
    });
  });

  it("сборка не удалась: сообщение и «Собрать ещё раз»", async () => {
    const start = vi
      .spyOn(packStudioApi, "startPreview")
      .mockRejectedValue(new ApiError("x", "preview_quota", 429, { limit: 2 }));
    renderSignatures(<ContentMain />, DOC, {
      before: () => {
        seedDocumentBuild(
          WS,
          { pack: "hse-cs-sse", template: "coursework", version: "2026.1.3" },
          SIGNATURES_DOC,
          null,
        );
      },
    });

    const failed = await screen.findByTestId("ct-sg-failed");
    expect(failed).toHaveTextContent("Не удалось собрать PDF");
    fireEvent.click(
      within(failed).getByRole("button", { name: /Собрать ещё раз/ }),
    );
    await vi.waitFor(() => {
      expect(start.mock.calls.length).toBeGreaterThanOrEqual(2);
    });
  });

  it("документа нет среди собираемых (презентация): PDF не будет, объяснение", async () => {
    renderSignatures(<ContentMain />, "doc=presentation&seg=signatures", {
      before: (client) => {
        // Подпись, которая относится к презентации.
        client.setQueryData(
          packStudioKeys.signatures(
            WS,
            { pack: "hse-cs-sse", template: "coursework", version: "2026.1.3" },
            null,
          ),
          {
            ...SIGNATURES_BUILT,
            build: null,
            slots: SIGNATURES_BUILT.slots.map((slot) => ({
              ...slot,
              applies_to: ["presentation"],
              document: null,
            })),
          },
        );
      },
    });

    expect(await screen.findByTestId("ct-sg-nopdf")).toHaveTextContent(
      "нет страниц для подписей",
    );
  });
});
