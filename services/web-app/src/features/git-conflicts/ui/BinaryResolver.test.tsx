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
  gitSyncApi,
  type ConflictFile,
  type FileResolution,
} from "@entities/git-sync";
import { i18n } from "@shared/lib/i18n";
import type { BinaryDetail } from "../model/conflictModel";
import { BinaryResolver } from "./BinaryResolver";

const PROJECT = "11111111-1111-4111-8111-111111111111";

const ME = {
  exists: true,
  size: 184_320,
  author: "Иван Смирнов",
  at: "2026-10-26T10:00:00Z",
};
const THEIRS = {
  exists: true,
  size: 2_048,
  author: "Анна Петрова",
  at: "2026-10-26T12:00:00Z",
};

const fileOf = (overrides: Partial<ConflictFile> = {}): ConflictFile => ({
  path: "images/architecture.png",
  owner: null,
  kind: "binary",
  action: "conflict",
  conflict_type: "binary",
  hunks: 0,
  open_hunks: 0,
  fields: 0,
  open_fields: 0,
  resolved: false,
  resolution: null,
  allowed: ["mine", "theirs", "newest"],
  default_resolution: "newest",
  sides: { ours: ME, theirs: THEIRS, base: ME },
  copy_path: "images/architecture.conflict-4f2a9c1.png",
  doc_id: null,
  ...overrides,
});

const detailOf = (overrides: Partial<BinaryDetail> = {}): BinaryDetail => ({
  kind: "binary",
  ours: ME,
  theirs: THEIRS,
  newer: "theirs",
  copy_path: "images/architecture.conflict-4f2a9c1.png",
  ...overrides,
});

const blobSpy = vi.spyOn(gitSyncApi, "getConflictBlob");

const renderResolver = (
  props: {
    file?: ConflictFile;
    detail?: BinaryDetail | undefined;
    resolution?: FileResolution | null;
  } = {},
) => {
  const onChoose = vi.fn();
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  });
  render(
    <QueryClientProvider client={client}>
      <BinaryResolver
        projectId={PROJECT}
        file={props.file ?? fileOf()}
        detail={"detail" in props ? props.detail : detailOf()}
        resolution={props.resolution ?? null}
        theirsAuthor="Анна Петрова"
        onChoose={onChoose}
      />
    </QueryClientProvider>,
  );
  return onChoose;
};

describe("BinaryResolver", () => {
  beforeEach(async () => {
    await i18n.changeLanguage("ru");
    blobSpy.mockReset();
    blobSpy.mockImplementation(() =>
      Promise.resolve(new Blob(["x"], { type: "image/png" })),
    );
  });
  afterEach(cleanup);

  it("shows both versions of a picture with a preview of each", async () => {
    renderResolver();
    const mine = await screen.findByAltText("Предпросмотр моей версии");
    const theirs = await screen.findByAltText(
      "Предпросмотр версии из репозитория",
    );
    expect((mine as HTMLImageElement).src).toMatch(/^data:/);
    expect((theirs as HTMLImageElement).src).toMatch(/^data:/);
    expect(blobSpy).toHaveBeenCalledWith(
      PROJECT,
      "images/architecture.png",
      "ours",
    );
    expect(blobSpy).toHaveBeenCalledWith(
      PROJECT,
      "images/architecture.png",
      "theirs",
    );
    // Кто и когда менял, и сколько весит.
    expect(screen.getByText(/Иван Смирнов/)).toBeInTheDocument();
    expect(screen.getByText(/180 КБ/)).toBeInTheDocument();
    expect(screen.getByText(/2\.0 КБ/)).toBeInTheDocument();
  });

  it("says which version is newer", () => {
    renderResolver();
    const tiles = document.querySelectorAll(".file-tile");
    expect(tiles).toHaveLength(2);
    expect(within(tiles[0] as HTMLElement).queryByText("новее")).toBeNull();
    expect(
      within(tiles[1] as HTMLElement).getByText("новее"),
    ).toBeInTheDocument();
  });

  it("explains what keeping the newer one does and names the copy", () => {
    renderResolver();
    expect(
      screen.getByText(/Останется более новая версия: Анна Петрова, /),
    ).toBeInTheDocument();
    expect(screen.getByText("рекомендуем")).toBeInTheDocument();
    expect(
      screen.getByText(/вторую версию Студия сохранит рядом/),
    ).toBeInTheDocument();
    expect(
      screen.getByDisplayValue("images/architecture.conflict-4f2a9c1.png"),
    ).toBeInTheDocument();
  });

  it("offers three radios and reports the choice", async () => {
    const user = userEvent.setup();
    const onChoose = renderResolver();
    expect(screen.getAllByRole("radio")).toHaveLength(3);
    await user.click(screen.getByRole("radio", { name: "Моя версия" }));
    expect(onChoose).toHaveBeenLastCalledWith("mine");
    await user.click(screen.getByRole("radio", { name: "Их (Анна Петрова)" }));
    expect(onChoose).toHaveBeenLastCalledWith("theirs");
    await user.click(
      screen.getByRole("radio", { name: /Оставить более новую/ }),
    );
    expect(onChoose).toHaveBeenLastCalledWith("newest");
  });

  it("marks the chosen version", () => {
    renderResolver({ resolution: { kind: "file", choice: "theirs" } });
    expect(
      screen.getByRole("radio", { name: "Их (Анна Петрова)" }),
    ).toBeChecked();
    expect(screen.getByRole("radio", { name: "Моя версия" })).not.toBeChecked();
  });

  it("hides the newest option and the copy when the server does not offer it", () => {
    renderResolver({
      file: fileOf({ allowed: ["mine", "theirs"], default_resolution: null }),
      detail: detailOf({ newer: "ours", copy_path: null }),
    });
    expect(screen.getAllByRole("radio")).toHaveLength(2);
    expect(screen.queryByText(/сохранит рядом/)).toBeNull();
  });

  it("does not preview what is not a picture", () => {
    renderResolver({
      file: fileOf({ path: "slides/defense.pptx", copy_path: null }),
      detail: detailOf({ copy_path: null }),
    });
    expect(blobSpy).not.toHaveBeenCalled();
    expect(
      screen.getAllByText("PPTX. Предпросмотра для этого вида файлов нет"),
    ).toHaveLength(2);
  });

  it("says so when a side has no file", () => {
    renderResolver({
      file: fileOf({ path: "images/a.png" }),
      detail: detailOf({ theirs: { ...THEIRS, exists: false, size: null } }),
    });
    expect(screen.getAllByText("Файла нет").length).toBeGreaterThan(0);
    // Для отсутствующей стороны ничего не запрашиваем.
    expect(blobSpy).toHaveBeenCalledTimes(1);
  });

  it("does not load a huge picture", () => {
    renderResolver({
      detail: detailOf({ ours: { ...ME, size: 50 * 1024 * 1024 } }),
    });
    expect(
      screen.getByText("Файл большой, предпросмотр не загружаем"),
    ).toBeInTheDocument();
    expect(blobSpy).toHaveBeenCalledTimes(1);
  });

  it("shows a note, not a broken image, when the preview fails", async () => {
    blobSpy.mockImplementation(() => Promise.reject(new Error("offline")));
    renderResolver();
    await waitFor(() => {
      expect(
        screen.getAllByText("Не удалось показать предпросмотр"),
      ).toHaveLength(2);
    });
    // Выбрать версию всё равно можно.
    expect(screen.getAllByRole("radio")).toHaveLength(3);
  });

  it("falls back to the file list data while the details are missing", () => {
    renderResolver({ detail: undefined });
    expect(screen.getAllByRole("radio")).toHaveLength(3);
    expect(
      screen.getByText("Останется та версия, которую изменили позже."),
    ).toBeInTheDocument();
  });

  it("speaks English", async () => {
    await i18n.changeLanguage("en");
    renderResolver();
    expect(
      screen.getByRole("radio", { name: "My version" }),
    ).toBeInTheDocument();
    expect(
      await screen.findByAltText("Preview of my version"),
    ).toBeInTheDocument();
    expect(screen.getByText("newer")).toBeInTheDocument();
  });
});
