import {
  cleanup,
  fireEvent,
  render,
  screen,
  waitFor,
  within,
} from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import type { ReactNode } from "react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { apiClient } from "@shared/api";
import { ApiError } from "@shared/api/client";
import { i18n } from "@shared/lib/i18n";
import { projectKeys } from "@entities/project";
import { useProjectFileUpload } from "../model/useProjectFileUpload";
import { FileUploadDialog } from "./FileUploadDialog";

// The `@shared/ui` barrel eagerly loads pdfjs-dist, which needs DOMMatrix.
vi.mock("pdfjs-dist", () => ({
  GlobalWorkerOptions: {},
  getDocument: () => ({ promise: Promise.resolve(null) }),
  version: "0",
}));

const PROJECT = "p-upload";
const AT = "2026-11-16T09:00:00Z";
const item = (path: string, isDir = false) => ({
  path,
  size: 3,
  modified_at: AT,
  deletable: true,
  is_dir: isDir,
});

const TREE = [item("img", true), item("img/a.png"), item("img/b.png")];

const Harness = ({ dest }: { dest: string }) => {
  const upload = useProjectFileUpload(PROJECT);
  return (
    <>
      <button
        type="button"
        onClick={() => {
          upload.pick(dest, "files");
        }}
      >
        pick
      </button>
      <FileUploadDialog upload={upload} />
    </>
  );
};

const setup = (project: Record<string, unknown> = {}) => {
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  });
  client.setQueryData(projectKeys.detail(PROJECT), {
    id: PROJECT,
    my_role: "editor",
    access: { mode: "full", reasons: [] },
    file_max_bytes: 10,
    storage: null,
    ...project,
  });
  vi.spyOn(apiClient, "get").mockImplementation((url: string) =>
    url === `/projects/${PROJECT}/files`
      ? Promise.resolve({ data: TREE })
      : new Promise(() => undefined),
  );
  const put = vi.spyOn(apiClient, "put").mockResolvedValue({ data: null });
  const wrapper = ({ children }: { children: ReactNode }) => (
    <QueryClientProvider client={client}>{children}</QueryClientProvider>
  );
  return { client, put, wrapper };
};

const png = (name: string, size = 3): File =>
  new File([new Uint8Array(size).fill(0xff)], name, { type: "image/png" });

const choose = async (
  user: ReturnType<typeof userEvent.setup>,
  files: File[],
) => {
  await user.click(screen.getByRole("button", { name: "pick" }));
  const input = screen.getByTestId("file-upload-input");
  Object.defineProperty(input, "files", { value: files, configurable: true });
  fireEvent.change(input);
};

const putPaths = (put: ReturnType<typeof setup>["put"]): string[] =>
  put.mock.calls.map(([url]) => url);

describe("FileUploadDialog", () => {
  beforeEach(async () => {
    await i18n.changeLanguage("ru");
  });
  afterEach(() => {
    cleanup();
    vi.restoreAllMocks();
  });

  it("sends each file as raw bytes to its encoded path", async () => {
    const user = userEvent.setup();
    const { put, wrapper } = setup();
    render(<Harness dest="img" />, { wrapper });
    const file = png("рис 1#.png");

    await choose(user, [file]);

    await waitFor(() => {
      expect(put).toHaveBeenCalledTimes(1);
    });
    const [url, body, config] = put.mock.calls[0] ?? [];
    expect(url).toBe(
      `/projects/${PROJECT}/files/img/${encodeURIComponent("рис 1#.png")}`,
    );
    expect(body).toBe(file);
    expect(config?.headers).toEqual({ "Content-Type": "image/png" });
    await waitFor(() => {
      expect(screen.queryByRole("dialog")).toBeNull();
    });
  });

  it("asks about an existing name and keeps both under a free name", async () => {
    const user = userEvent.setup();
    const { put, wrapper } = setup();
    render(<Harness dest="img" />, { wrapper });

    await choose(user, [png("a.png"), png("c.png")]);

    const dialog = await screen.findByRole("dialog", { name: "Файл уже есть" });
    expect(within(dialog).getByText("img/a.png")).toBeTruthy();
    await user.click(
      within(dialog).getByRole("button", { name: "Оставить оба" }),
    );

    await waitFor(() => {
      expect(putPaths(put)).toEqual([
        `/projects/${PROJECT}/files/img/a%20(1).png`,
        `/projects/${PROJECT}/files/img/c.png`,
      ]);
    });
  });

  it("applies one answer to all matches", async () => {
    const user = userEvent.setup();
    const { put, wrapper } = setup();
    render(<Harness dest="img" />, { wrapper });

    await choose(user, [png("a.png"), png("b.png")]);

    const dialog = await screen.findByRole("dialog", { name: "Файл уже есть" });
    await user.click(within(dialog).getByRole("checkbox"));
    await user.click(within(dialog).getByRole("button", { name: "Заменить" }));

    await waitFor(() => {
      expect(putPaths(put)).toEqual([
        `/projects/${PROJECT}/files/img/a.png`,
        `/projects/${PROJECT}/files/img/b.png`,
      ]);
    });
  });

  it("refuses too large files before sending and shows server refusals", async () => {
    const user = userEvent.setup();
    const { put, wrapper } = setup();
    put.mockImplementation((url: string) =>
      url.endsWith("/locked.png")
        ? Promise.reject(new ApiError("нет", "forbidden", 403))
        : Promise.resolve({ data: null }),
    );
    render(<Harness dest="" />, { wrapper });

    await choose(user, [png("huge.png", 11), png("locked.png"), png("ok.png")]);

    const dialog = await screen.findByRole("dialog", { name: "Итог загрузки" });
    expect(putPaths(put)).toEqual([
      `/projects/${PROJECT}/files/locked.png`,
      `/projects/${PROJECT}/files/ok.png`,
    ]);
    expect(within(dialog).getByText("Загружено 1 из 3.")).toBeTruthy();
    const failures = within(dialog).getByTestId("upload-failures");
    expect(within(failures).getByText("huge.png")).toBeTruthy();
    expect(
      within(failures).getByText("Файл больше 10 Б: сервер такой не примет."),
    ).toBeTruthy();
    expect(
      within(failures).getByText("Нет права записи в эту папку."),
    ).toBeTruthy();
  });

  it("stops the batch when the project is out of space", async () => {
    const user = userEvent.setup();
    const { put, wrapper } = setup();
    put.mockRejectedValue(
      new ApiError("нет места", "project_quota_exceeded", 413),
    );
    render(<Harness dest="" />, { wrapper });

    await choose(user, [png("x.png"), png("y.png")]);

    const dialog = await screen.findByRole("dialog", { name: "Итог загрузки" });
    expect(put).toHaveBeenCalledTimes(1);
    expect(
      within(dialog).getByText("В проекте закончилось место."),
    ).toBeTruthy();
    expect(
      within(dialog).getByText(
        "Не загружен: загрузка остановлена после ошибки выше.",
      ),
    ).toBeTruthy();
  });
});
