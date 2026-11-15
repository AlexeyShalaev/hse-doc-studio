import { cleanup, render, screen } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import type { ReactNode } from "react";
import { MemoryRouter } from "react-router";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import type { z } from "zod";
import type { DocumentResponseSchema } from "@entities/document";
import type * as SharedUi from "@shared/ui";
import type * as AppSettingsModule from "@entities/app-settings";
import type * as SignatureModule from "@entities/signature";
import type * as SessionModule from "@entities/session";
import type * as PdfReviewModule from "@features/pdf-review";
import type * as DocumentModule from "@entities/document";
import type { ProjectResponseSchema } from "@entities/project";
import { i18n } from "@shared/lib/i18n";
import { PreviewPane } from "./PreviewPane";

// The `@shared/ui` barrel eagerly loads pdfjs-dist, which needs DOMMatrix.
vi.mock("pdfjs-dist", () => ({
  GlobalWorkerOptions: {},
  getDocument: () => ({ promise: Promise.resolve(null) }),
  version: "0",
}));

// Превью по статусу документа: `err` ставят и упавшая сборка, и ошибки проверок
// при готовом PDF. Прод 0.31.0: сборка в облаке прошла, проверки нашли ошибку,
// а превью показывало «Документ ещё не компилировался» вместо PDF.

type Doc = z.infer<typeof DocumentResponseSchema>;
type Project = z.infer<typeof ProjectResponseSchema>;
type CompileStub = { id: string; status: string; started_at: string };

const compiles = vi.hoisted(() => ({ list: [] as CompileStub[] }));

vi.mock("@shared/ui", async (importOriginal) => ({
  ...(await importOriginal<typeof SharedUi>()),
  PdfViewer: ({
    url,
    toolbarExtras,
  }: {
    url: string;
    toolbarExtras?: ReactNode;
  }) => (
    <div data-testid="pdf-viewer" data-url={url}>
      {toolbarExtras}
    </div>
  ),
  PdfDiffView: () => <div data-testid="pdf-diff" />,
}));
vi.mock("@entities/app-settings", async (importOriginal) => ({
  ...(await importOriginal<typeof AppSettingsModule>()),
  useAppSettings: () => ({
    data: { default_engine: "xelatex", latex_passes: 3 },
  }),
}));
vi.mock("@entities/signature", async (importOriginal) => ({
  ...(await importOriginal<typeof SignatureModule>()),
  useSignaturesState: () => ({ data: undefined }),
}));
vi.mock("@entities/session", async (importOriginal) => ({
  ...(await importOriginal<typeof SessionModule>()),
  useBootstrap: () => ({ data: { mode: "server", user: null } }),
}));
vi.mock("@entities/synctex", () => ({ synctexApi: { inverse: vi.fn() } }));
vi.mock("@features/pdf-review", async (importOriginal) => ({
  ...(await importOriginal<typeof PdfReviewModule>()),
  usePdfReview: () => ({ panel: null, viewer: {}, toolbar: null }),
}));
vi.mock("@entities/document", async (importOriginal) => ({
  ...(await importOriginal<typeof DocumentModule>()),
  useCompiles: () => ({ data: compiles.list }),
}));

const PROJECT = {
  id: "p1",
  lang: "ru",
  my_role: null,
} as unknown as Project;

const makeDoc = (over: Partial<Doc>): Doc => ({
  id: "project_proposal",
  status: "err",
  engine: "xelatex",
  source_file: "project_proposal/project_proposal.tex",
  output_file: "project_proposal/project_proposal.pdf",
  last_compile_id: "c-2",
  ...over,
});

const renderPane = (doc: Doc) => {
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  });
  render(
    <QueryClientProvider client={client}>
      <MemoryRouter>
        <PreviewPane project={PROJECT} doc={doc} />
      </MemoryRouter>
    </QueryClientProvider>,
  );
};

describe("PreviewPane: what is shown for a document status", () => {
  beforeEach(async () => {
    await i18n.changeLanguage("ru");
    compiles.list = [
      { id: "c-2", status: "success", started_at: "2026-11-16T09:00:00Z" },
    ];
  });
  afterEach(() => {
    cleanup();
  });

  it("shows the built PDF when the build succeeded but checks found errors", () => {
    renderPane(
      makeDoc({ last_compile_status: "success", output_available: true }),
    );

    expect(screen.getByTestId("pdf-viewer").dataset.url).toContain(
      "/projects/p1/files/project_proposal/project_proposal.pdf",
    );
    expect(screen.getByTestId("preview-build-notice").textContent).toBe(
      "PDF собран, но проверки нашли ошибки. Список во вкладке «Замечания».",
    );
    expect(screen.queryByText(/ещё не компилировался/)).toBeNull();
  });

  it("keeps the PDF of an earlier build after a failed one and says so", () => {
    renderPane(
      makeDoc({ last_compile_status: "failure", output_available: true }),
    );

    expect(screen.getByTestId("pdf-viewer")).toBeInTheDocument();
    expect(screen.getByTestId("preview-build-notice").textContent).toContain(
      "Показан PDF прошлой удачной сборки",
    );
  });

  it("marks a PDF of an earlier build after a cancelled one too", () => {
    renderPane(
      makeDoc({ last_compile_status: "cancelled", output_available: true }),
    );

    expect(screen.getByTestId("pdf-viewer")).toBeInTheDocument();
    expect(screen.getByTestId("preview-build-notice")).toBeInTheDocument();
  });

  it("shows a clean PDF without a notice for a successful build", () => {
    renderPane(
      makeDoc({
        status: "ok",
        last_compile_status: "success",
        output_available: true,
      }),
    );

    expect(screen.getByTestId("pdf-viewer")).toBeInTheDocument();
    expect(screen.queryByTestId("preview-build-notice")).toBeNull();
  });

  it("keeps showing the current PDF while a rebuild runs", () => {
    renderPane(
      makeDoc({
        status: "building",
        last_compile_status: "running",
        output_available: true,
      }),
    );

    expect(screen.getByTestId("pdf-viewer")).toBeInTheDocument();
  });

  it("says the last build failed, not 'never compiled', when there is no PDF yet", () => {
    renderPane(
      makeDoc({ last_compile_status: "failure", output_available: false }),
    );

    expect(screen.queryByTestId("pdf-viewer")).toBeNull();
    expect(screen.getByText("нет PDF")).toBeInTheDocument();
    expect(
      screen.getByText(/PDF пока нет: последняя сборка не удалась/),
    ).toBeInTheDocument();
    expect(screen.queryByText(/ещё не компилировался/)).toBeNull();
  });

  it("says the document is being built during its first build", () => {
    renderPane(
      makeDoc({
        status: "building",
        last_compile_status: "running",
        output_available: false,
      }),
    );

    expect(screen.getByText(/Документ собирается/)).toBeInTheDocument();
    expect(screen.queryByText(/ещё не компилировался/)).toBeNull();
  });

  it("offers the first build only when there were no compiles at all", () => {
    compiles.list = [];
    renderPane(
      makeDoc({
        status: "draft",
        last_compile_id: null,
        last_compile_status: null,
        output_available: false,
      }),
    );

    expect(screen.getByText("не собран")).toBeInTheDocument();
    expect(
      screen.getByText(/Документ ещё не компилировался/),
    ).toBeInTheDocument();
  });

  it("falls back to the status when the server does not report the file", () => {
    renderPane(makeDoc({ status: "warn" }));

    expect(screen.getByTestId("pdf-viewer")).toBeInTheDocument();
  });
});
