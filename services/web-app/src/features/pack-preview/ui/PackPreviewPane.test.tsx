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
const build = (name: string) =>
  fixture(PackPreviewBuildSchema, "PackPreviewBuild", name);
const WS = OPTIONS.workspace_id;
const FILE = "hse-cs-sse/templates/coursework/versions/2026.1.7/version.yaml";
const REF = { pack: "hse-cs-sse", template: "coursework", version: "2026.1.7" };

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
  });
  afterEach(() => {
    vi.restoreAllMocks();
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
    expect(error).toHaveTextContent("Версию шаблона не удалось разобрать");
    expect(error).toHaveTextContent("ValueError: version.yaml не разобран");
  });
});
