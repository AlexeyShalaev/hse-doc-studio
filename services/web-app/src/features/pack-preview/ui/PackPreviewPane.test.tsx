import { readFileSync } from "node:fs";
import { join } from "node:path";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeAll, describe, expect, it, vi } from "vitest";
import type { ZodType } from "zod";
import {
  PackPreviewBuildSchema,
  PackPreviewOptionsSchema,
  packStudioApi,
} from "@entities/pack-studio";
import { ApiError } from "@shared/api";
import { i18n } from "@shared/lib";
import { loadPackStudioNamespace } from "@shared/lib/i18n/packStudioNamespace";
import { resetPreviewSelections } from "../lib/selection";
import { PackPreviewPane } from "./PackPreviewPane";

// pdf.js в jsdom не поднимается: просмотрщик подменён адресом файла.
vi.mock("@shared/ui", async () => ({
  ...(await vi.importActual<Record<string, unknown>>("@shared/ui")),
  PdfViewer: ({ url }: { url: string }) => (
    <div data-testid="pdf-viewer" data-url={url} />
  ),
}));

const FIXTURES = join(
  import.meta.dirname,
  "../../../../../../contracts/pack-studio/fixtures",
);
const fixture = <T,>(schema: ZodType<T>, dir: string, name: string): T =>
  schema.parse(
    JSON.parse(readFileSync(join(FIXTURES, dir, `${name}.json`), "utf8")),
  );

const OPTIONS = fixture(
  PackPreviewOptionsSchema,
  "PackPreviewOptions",
  "coursework",
);
const OPTIONS_VARIANTS = fixture(
  PackPreviewOptionsSchema,
  "PackPreviewOptions",
  "with_variants",
);
const build = (name: string) =>
  fixture(PackPreviewBuildSchema, "PackPreviewBuild", name);
const WS = OPTIONS.workspace_id;
const FILE = "hse-cs-sse/templates/coursework/versions/2026.1.7/version.yaml";
const REF = { pack: "hse-cs-sse", template: "coursework", version: "2026.1.7" };

const VKR_FILE = "hse-cs-se/templates/vkr/versions/2026.1.2/version.yaml";
const VKR_REF = { pack: "hse-cs-se", template: "vkr", version: "2026.1.2" };

const mount = (path = FILE, revision = 0) => {
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  });
  const view = render(
    <QueryClientProvider client={client}>
      <PackPreviewPane workspaceId={WS} path={path} revision={revision} />
    </QueryClientProvider>,
  );
  return {
    rerender: (next: number) => {
      view.rerender(
        <QueryClientProvider client={client}>
          <PackPreviewPane workspaceId={WS} path={path} revision={next} />
        </QueryClientProvider>,
      );
    },
  };
};

describe("предпросмотр версии шаблона", () => {
  beforeAll(async () => {
    await loadPackStudioNamespace();
    await i18n.changeLanguage("ru");
    // Radix Select ловит указатель; в jsdom этих методов нет.
    const proto = Element.prototype as Partial<Element> & {
      hasPointerCapture?: (id: number) => boolean;
      releasePointerCapture?: (id: number) => void;
      scrollIntoView?: () => void;
    };
    proto.hasPointerCapture ??= () => false;
    proto.releasePointerCapture ??= () => undefined;
    proto.scrollIntoView ??= () => undefined;
  });
  afterEach(() => {
    vi.restoreAllMocks();
    resetPreviewSelections();
  });

  it("файл вне версии: пояснение без запросов", () => {
    const options = vi.spyOn(packStudioApi, "previewOptions");
    mount("hse-cs-sse/pack.yaml");
    expect(screen.getByTestId("preview-outside")).toBeInTheDocument();
    expect(options).not.toHaveBeenCalled();
  });

  it("сборка с набором и комбинацией по умолчанию, опрос до PDF, журнал", async () => {
    vi.spyOn(packStudioApi, "previewOptions").mockResolvedValue(OPTIONS);
    const queued = build("queued");
    const start = vi
      .spyOn(packStudioApi, "startPreview")
      .mockResolvedValue([queued]);
    const done = build("succeeded");
    const poll = vi
      .spyOn(packStudioApi, "previewBuild")
      .mockResolvedValueOnce(queued)
      .mockResolvedValue({ ...done, id: queued.id });
    vi.spyOn(packStudioApi, "previewLog").mockResolvedValue(
      "[render] предупреждение\nOutput written",
    );
    const { rerender } = mount();
    // Документ «Заявка» подходит к виду project: он выбран первым.
    await userEvent.click(await screen.findByTestId("preview-build"));
    await waitFor(() => {
      expect(start).toHaveBeenCalledWith(WS, REF, {
        documents: ["project_proposal"],
        example: "approval-gate",
        combination: OPTIONS.combination,
      });
    });
    expect(await screen.findByTestId("preview-running")).toHaveTextContent(
      "В очереди",
    );
    const viewer = await screen.findByTestId(
      "pdf-viewer",
      {},
      { timeout: 4000 },
    );
    expect(poll).toHaveBeenCalledWith(WS, queued.id);
    expect(viewer.getAttribute("data-url")).toContain(
      `/api/v1/pack-studio/workspaces/${WS}/previews/${queued.id}/pdf`,
    );
    await userEvent.click(screen.getByTestId("preview-log-open"));
    expect(await screen.findByTestId("preview-log")).toHaveTextContent(
      "[render] предупреждение",
    );
    // Правка после сборки: PDF помечен устаревшим.
    rerender(1);
    expect(
      await screen.findByText(/Файлы менялись после этой сборки/),
    ).toBeInTheDocument();
  });

  it("документ без вариантов: выбора варианта нет, в запросе нет поля variant", async () => {
    vi.spyOn(packStudioApi, "previewOptions").mockResolvedValue(OPTIONS);
    const start = vi
      .spyOn(packStudioApi, "startPreview")
      .mockResolvedValue([build("queued")]);
    mount();
    await userEvent.click(await screen.findByTestId("preview-build"));
    await waitFor(() => {
      expect(start).toHaveBeenCalled();
    });
    expect(
      screen.queryByRole("combobox", { name: "Вариант документа" }),
    ).not.toBeInTheDocument();
    expect(start.mock.calls[0]?.[2]).not.toHaveProperty("variant");
  });

  it("прежний сервер без полей вариантов: экран работает как раньше", async () => {
    const legacy = {
      ...OPTIONS_VARIANTS,
      documents: OPTIONS_VARIANTS.documents.map((doc) => ({
        id: doc.id,
        name: doc.name,
        kinds: doc.kinds,
        staffing: doc.staffing,
      })),
    };
    vi.spyOn(packStudioApi, "previewOptions").mockResolvedValue(legacy);
    const start = vi
      .spyOn(packStudioApi, "startPreview")
      .mockResolvedValue([build("queued")]);
    mount(VKR_FILE);
    await userEvent.click(await screen.findByTestId("preview-build"));
    await waitFor(() => {
      expect(start).toHaveBeenCalled();
    });
    expect(
      screen.queryByRole("combobox", { name: "Вариант документа" }),
    ).not.toBeInTheDocument();
    expect(start.mock.calls[0]?.[2]).not.toHaveProperty("variant");
  });

  it("документ с вариантами: выбор варианта, по умолчанию первый, в запросе variant", async () => {
    vi.spyOn(packStudioApi, "previewOptions").mockResolvedValue(
      OPTIONS_VARIANTS,
    );
    const start = vi
      .spyOn(packStudioApi, "startPreview")
      .mockResolvedValue([build("queued")]);
    mount(VKR_FILE);
    const select = await screen.findByRole("combobox", {
      name: "Вариант документа",
    });
    expect(select).toHaveTextContent("ГОСТ 19 ЕСПД (ТЗ)");
    await userEvent.click(screen.getByTestId("preview-build"));
    await waitFor(() => {
      expect(start).toHaveBeenCalledWith(WS, VKR_REF, {
        documents: ["technical_specification"],
        example: "auto:normal",
        combination: OPTIONS_VARIANTS.combination,
        variant: "espd",
      });
    });
  });

  it("вариант только для другого языка недоступен в списке", async () => {
    vi.spyOn(packStudioApi, "previewOptions").mockResolvedValue(
      OPTIONS_VARIANTS,
    );
    mount(VKR_FILE);
    await userEvent.click(
      await screen.findByRole("combobox", { name: "Вариант документа" }),
    );
    const iso = await screen.findByRole("option", {
      name: /ISO\/IEC\/IEEE 29148 \(SRS\) \(только en\)/,
    });
    expect(iso).toHaveAttribute("aria-disabled", "true");
  });

  it("выбранный вариант другого документа уходит в сборку, у варианта без PDF есть подсказка", async () => {
    vi.spyOn(packStudioApi, "previewOptions").mockResolvedValue(
      OPTIONS_VARIANTS,
    );
    const start = vi
      .spyOn(packStudioApi, "startPreview")
      .mockResolvedValue([build("queued")]);
    mount(VKR_FILE);
    await userEvent.click(
      await screen.findByRole("combobox", { name: "Документ" }),
    );
    await userEvent.click(
      await screen.findByRole("option", { name: "Презентация защиты" }),
    );
    const variant = await screen.findByRole("combobox", {
      name: "Вариант документа",
    });
    expect(variant).toHaveTextContent("PowerPoint-шаблон");
    await userEvent.click(variant);
    await userEvent.click(
      await screen.findByRole("option", { name: "RevealJS (HTML)" }),
    );
    expect(
      await screen.findByText(/Из этого варианта PDF не собирается/),
    ).toBeInTheDocument();
    await userEvent.click(
      screen.getByRole("combobox", { name: "Вариант документа" }),
    );
    await userEvent.click(
      await screen.findByRole("option", { name: "LaTeX Beamer" }),
    );
    expect(
      screen.queryByText(/Из этого варианта PDF не собирается/),
    ).not.toBeInTheDocument();
    await userEvent.click(screen.getByTestId("preview-build"));
    await waitFor(() => {
      expect(start).toHaveBeenCalledWith(
        WS,
        VKR_REF,
        expect.objectContaining({
          documents: ["presentation"],
          variant: "beamer",
        }),
      );
    });
  });

  it("неудачная сборка: текст по коду, подробность и журнал", async () => {
    vi.spyOn(packStudioApi, "previewOptions").mockResolvedValue(OPTIONS);
    const failed = build("render_failed");
    vi.spyOn(packStudioApi, "startPreview").mockResolvedValue([failed]);
    mount();
    await userEvent.click(await screen.findByTestId("preview-build"));
    const text = await screen.findByTestId("preview-failed");
    expect(text).toHaveTextContent("Шаблон пака не отрисовался");
    expect(text).toHaveTextContent("рендер дольше 30.0 с");
  });

  it("отмена идущей сборки", async () => {
    vi.spyOn(packStudioApi, "previewOptions").mockResolvedValue(OPTIONS);
    const running = build("running");
    vi.spyOn(packStudioApi, "startPreview").mockResolvedValue([running]);
    vi.spyOn(packStudioApi, "previewBuild").mockResolvedValue(running);
    const cancel = vi
      .spyOn(packStudioApi, "cancelPreview")
      .mockResolvedValue({ ...running, status: "cancelled" });
    mount();
    await userEvent.click(await screen.findByTestId("preview-build"));
    await userEvent.click(await screen.findByTestId("preview-cancel"));
    await waitFor(() => {
      expect(cancel).toHaveBeenCalledWith(WS, running.id);
    });
    expect(await screen.findByTestId("preview-cancelled")).toBeInTheDocument();
  });

  it("предел параллельных сборок: понятное сообщение с числом", async () => {
    vi.spyOn(packStudioApi, "previewOptions").mockResolvedValue(OPTIONS);
    vi.spyOn(packStudioApi, "startPreview").mockRejectedValue(
      new ApiError("x", "preview_quota", 429, { limit: 2 }),
    );
    mount();
    await userEvent.click(await screen.findByTestId("preview-build"));
    expect(await screen.findByRole("alert")).toHaveTextContent(
      "Сейчас идут 2 сборки предпросмотра",
    );
  });

  it("версию не разобрать: текст и причина", async () => {
    vi.spyOn(packStudioApi, "previewOptions").mockRejectedValue(
      new ApiError("x", "version_unreadable", 422, {
        reason: "ValueError: version.yaml не разобран",
      }),
    );
    mount();
    const error = await screen.findByTestId("preview-options-error");
    expect(error).toHaveTextContent("Описание версии не удалось разобрать");
    expect(error).toHaveTextContent("ValueError: version.yaml не разобран");
  });
});
