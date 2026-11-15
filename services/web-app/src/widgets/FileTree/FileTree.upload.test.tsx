import {
  cleanup,
  fireEvent,
  render,
  screen,
  waitFor,
} from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import type { ReactNode } from "react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { apiClient } from "@shared/api";
import { i18n } from "@shared/lib/i18n";
import { fileKeys } from "@entities/document";
import { FileTree, type FileTreeUpload } from "./FileTree";

// The `@shared/ui` barrel eagerly loads pdfjs-dist, which needs DOMMatrix.
vi.mock("pdfjs-dist", () => ({
  GlobalWorkerOptions: {},
  getDocument: () => ({ promise: Promise.resolve(null) }),
  version: "0",
}));

const PROJECT = "p-tree";
const AT = "2026-11-16T09:00:00Z";
const item = (path: string, isDir = false) => ({
  path,
  size: 3,
  modified_at: AT,
  deletable: true,
  is_dir: isDir,
});

const externalDrag = (): DataTransfer =>
  ({
    types: ["Files"],
    items: [],
    files: [],
    dropEffect: "none",
    getData: () => "",
  }) as unknown as DataTransfer;

const internalDrag = (src: string): DataTransfer =>
  ({
    types: ["application/x-hse-path"],
    dropEffect: "none",
    getData: (type: string) => (type === "application/x-hse-path" ? src : ""),
  }) as unknown as DataTransfer;

const renderTree = (enabled = true) => {
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  });
  client.setQueryData(fileKeys.tree(PROJECT), [
    item("img", true),
    item("img/a.png"),
    item("main.tex"),
    item("figure.pdf"),
    item("main.pdf"),
  ]);
  vi.spyOn(apiClient, "get").mockImplementation(
    () => new Promise(() => undefined),
  );
  const move = vi.spyOn(apiClient, "post").mockResolvedValue({ data: null });
  const upload: FileTreeUpload = { enabled, pick: vi.fn(), drop: vi.fn() };
  const wrapper = ({ children }: { children: ReactNode }) => (
    <QueryClientProvider client={client}>{children}</QueryClientProvider>
  );
  render(
    <FileTree
      projectId={PROJECT}
      selectedPath={undefined}
      onSelect={vi.fn()}
      upload={upload}
    />,
    { wrapper },
  );
  return { upload, move };
};

describe("FileTree upload", () => {
  beforeEach(async () => {
    await i18n.changeLanguage("ru");
  });
  afterEach(() => {
    cleanup();
    vi.restoreAllMocks();
  });

  it("drops files from the computer into a folder, the root and next to a file", () => {
    const { upload } = renderTree();

    const toFolder = externalDrag();
    fireEvent.dragOver(screen.getByText("img"), { dataTransfer: toFolder });
    fireEvent.drop(screen.getByText("img"), { dataTransfer: toFolder });
    expect(upload.drop).toHaveBeenLastCalledWith(toFolder, "img");

    const nextToFile = externalDrag();
    fireEvent.drop(screen.getByText("a.png"), { dataTransfer: nextToFile });
    expect(upload.drop).toHaveBeenLastCalledWith(nextToFile, "img");

    const toRoot = externalDrag();
    const root = screen.getByTestId("file-tree-root");
    fireEvent.dragOver(root, { dataTransfer: toRoot });
    expect(root.getAttribute("title")).toBe(
      "Отпустите, чтобы загрузить в корень проекта",
    );
    fireEvent.drop(root, { dataTransfer: toRoot });
    expect(upload.drop).toHaveBeenLastCalledWith(toRoot, "");
  });

  it("keeps moving rows inside the tree as before", async () => {
    const { upload, move } = renderTree();

    fireEvent.drop(screen.getByText("img"), {
      dataTransfer: internalDrag("main.tex"),
    });

    expect(upload.drop).not.toHaveBeenCalled();
    await waitFor(() => {
      expect(move).toHaveBeenCalledWith(`/projects/${PROJECT}/file-ops/move`, {
        src: "main.tex",
        dst: "img/main.tex",
      });
    });
  });

  it("offers «upload here» in the folder and root menus", async () => {
    const user = userEvent.setup();
    const { upload } = renderTree();

    fireEvent.contextMenu(screen.getByText("img"));
    await user.click(
      screen.getByRole("button", { name: "Загрузить файлы сюда" }),
    );
    expect(upload.pick).toHaveBeenLastCalledWith("img", "files");

    fireEvent.contextMenu(screen.getByTestId("file-tree-root"));
    await user.click(
      screen.getByRole("button", { name: "Загрузить папку сюда" }),
    );
    expect(upload.pick).toHaveBeenLastCalledWith("", "folder");
  });

  it("does not accept files without the write right", () => {
    const { upload } = renderTree(false);

    fireEvent.drop(screen.getByText("img"), { dataTransfer: externalDrag() });
    fireEvent.contextMenu(screen.getByText("img"));

    expect(upload.drop).not.toHaveBeenCalled();
    expect(
      screen.queryByRole("button", { name: "Загрузить файлы сюда" }),
    ).toBeNull();
  });

  it("shows a user PDF and hides the one built next to its source", () => {
    renderTree();

    expect(screen.getByText("figure.pdf")).toBeTruthy();
    expect(screen.queryByText("main.pdf")).toBeNull();
  });
});
