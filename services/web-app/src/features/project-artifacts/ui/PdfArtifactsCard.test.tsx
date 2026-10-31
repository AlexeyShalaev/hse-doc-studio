import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import {
  cleanup,
  render,
  screen,
  waitFor,
  within,
} from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import {
  projectArtifactApi,
  type ProjectArtifact,
  type ProjectArtifactList,
} from "@entities/project-artifact";
import { toast } from "@shared/lib";
import { i18n } from "@shared/lib/i18n";

vi.mock("@shared/ui", async () => ({
  ...(await vi.importActual<Record<string, unknown>>("@shared/ui")),
  PdfViewer: ({ url }: { url: string }) => (
    <div data-testid="pdf-viewer" data-url={url} />
  ),
}));

import { PdfArtifactsCard } from "./PdfArtifactsCard";

const PROJECT = "5b0c1d2e-3f40-4152-8364-758697a8b9c0";

const artifact = (
  id: string,
  patch: Partial<ProjectArtifact> = {},
): ProjectArtifact => ({
  id,
  kind: "pdf",
  doc_id: "coursework",
  file_name: "coursework.pdf",
  size: 482_113,
  sha256: "a".repeat(64),
  pages: 42,
  source_commit: null,
  built_at: null,
  uploaded_at: "2026-11-02T10:00:00Z",
  uploaded_by_name: "Анна Петрова",
  client_name: "Студия на MacBook",
  file_url: `/api/v1/projects/${PROJECT}/artifacts/${id}/file`,
  ...patch,
});

const list = (items: ProjectArtifact[]): ProjectArtifactList => ({
  items,
  max_pdf_bytes: 104_857_600,
  keep_per_document: 5,
});

const mount = (props: { canDelete?: boolean } = {}) => {
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  });
  return render(
    <QueryClientProvider client={client}>
      <PdfArtifactsCard projectId={PROJECT} {...props} />
    </QueryClientProvider>,
  );
};

describe("PdfArtifactsCard", () => {
  beforeEach(async () => {
    await i18n.changeLanguage("ru");
  });
  afterEach(() => {
    cleanup();
    vi.restoreAllMocks();
  });

  it("renders nothing while no PDF has been uploaded", async () => {
    const spy = vi
      .spyOn(projectArtifactApi, "list")
      .mockResolvedValue(list([]));

    const { container } = mount();

    await waitFor(() => {
      expect(spy).toHaveBeenCalled();
    });
    expect(
      container.querySelector("[data-testid='pdf-artifacts-card']"),
    ).toBeNull();
  });

  it("shows the latest PDF of a document with who uploaded it and keeps older ones folded", async () => {
    vi.spyOn(projectArtifactApi, "list").mockResolvedValue(
      list([
        artifact("new"),
        artifact("old", { uploaded_at: "2026-11-01T10:00:00Z", pages: 40 }),
      ]),
    );

    mount();

    const rows = await screen.findAllByTestId("artifact-row");
    expect(rows).toHaveLength(2);
    const first = within(rows[0]!);
    expect(first.getByText("coursework.pdf")).toBeTruthy();
    expect(first.getByText(/42 стр\./)).toBeTruthy();
    expect(first.getByText(/выгрузил Анна Петрова/)).toBeTruthy();
    expect(first.getByText(/из «Студия на MacBook»/)).toBeTruthy();
    expect(screen.getByText("Предыдущие версии: 1")).toBeTruthy();
  });

  it("downloads through the authorized file address and opens the PDF in the viewer", async () => {
    const user = userEvent.setup();
    vi.spyOn(projectArtifactApi, "list").mockResolvedValue(
      list([artifact("new")]),
    );
    mount();

    const link = await screen.findByRole("link", { name: "Скачать" });
    expect(link.getAttribute("href")).toContain(
      `/api/v1/projects/${PROJECT}/artifacts/new/file`,
    );
    expect(link.getAttribute("download")).toBe("coursework.pdf");

    await user.click(screen.getByRole("button", { name: "Открыть" }));

    const viewer = await screen.findByTestId("pdf-viewer");
    expect(viewer.getAttribute("data-url")).toContain("/artifacts/new/file");
  });

  it("hides deletion from people who cannot write", async () => {
    vi.spyOn(projectArtifactApi, "list").mockResolvedValue(
      list([artifact("new")]),
    );

    mount();

    await screen.findByTestId("artifact-row");
    expect(screen.queryByRole("button", { name: "Удалить" })).toBeNull();
  });

  it("deletes after confirmation and refreshes the list", async () => {
    const user = userEvent.setup();
    const listSpy = vi
      .spyOn(projectArtifactApi, "list")
      .mockResolvedValueOnce(list([artifact("new")]))
      .mockResolvedValue(list([]));
    const remove = vi
      .spyOn(projectArtifactApi, "remove")
      .mockResolvedValue(undefined);
    vi.spyOn(window, "confirm").mockReturnValue(true);
    mount({ canDelete: true });

    await user.click(await screen.findByRole("button", { name: "Удалить" }));

    await waitFor(() => {
      expect(remove).toHaveBeenCalledWith(PROJECT, "new");
    });
    await waitFor(() => {
      expect(listSpy.mock.calls.length).toBeGreaterThan(1);
    });
  });

  it("does not delete without confirmation and tells when the server refuses", async () => {
    const user = userEvent.setup();
    vi.spyOn(projectArtifactApi, "list").mockResolvedValue(
      list([artifact("new")]),
    );
    const remove = vi
      .spyOn(projectArtifactApi, "remove")
      .mockRejectedValue(new Error("403"));
    const error = vi.spyOn(toast, "error").mockReturnValue("t");
    const confirm = vi.spyOn(window, "confirm").mockReturnValue(false);
    mount({ canDelete: true });
    const button = await screen.findByRole("button", { name: "Удалить" });

    await user.click(button);
    expect(remove).not.toHaveBeenCalled();

    confirm.mockReturnValue(true);
    await user.click(button);
    await waitFor(() => {
      expect(error).toHaveBeenCalledWith("Не удалось удалить PDF");
    });
  });
});
