import { readFileSync } from "node:fs";
import { join } from "node:path";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeAll, describe, expect, it, vi } from "vitest";
import type { ZodType } from "zod";
import {
  PackReleaseSchema,
  PackStudioErrorBodySchema,
  PackVersionCreatedSchema,
  PackVersionMovedSchema,
  PackVersionOptionsSchema,
  PackVersionStateSchema,
  packStudioApi,
  type PackVersionState,
} from "@entities/pack-studio";
import { ApiError } from "@shared/api";
import { i18n } from "@shared/lib";
import { loadPackStudioNamespace } from "@shared/lib/i18n/packStudioNamespace";
import { NewVersionDialog } from "./NewVersionDialog";
import { VersionBar } from "./VersionBar";

const FIXTURES = join(
  import.meta.dirname,
  "../../../../../../contracts/pack-studio/fixtures",
);
const fixture = <T,>(schema: ZodType<T>, dir: string, name: string): T =>
  schema.parse(
    JSON.parse(readFileSync(join(FIXTURES, dir, `${name}.json`), "utf8")),
  );

const apiError = (name: string, status = 409): ApiError => {
  const body = fixture(PackStudioErrorBodySchema, "PackStudioErrorBody", name);
  const { detail, code, ...data } = body;
  return new ApiError(detail, code, status, data);
};

const DRAFT = fixture(
  PackVersionStateSchema,
  "PackVersionState",
  "draft_minor",
);
const RELEASED = fixture(
  PackVersionStateSchema,
  "PackVersionState",
  "released_modified",
);
const DRAFT_FILE = `${DRAFT.version.path}/files/report/main.tex`;

const client = () =>
  new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  });

const mountBar = (state: PackVersionState, path = DRAFT_FILE) => {
  vi.spyOn(packStudioApi, "versionState").mockResolvedValue(state);
  const props = {
    onOpenFile: vi.fn(),
    onNewVersion: vi.fn(),
    onFilesChanged: vi.fn(),
  };
  render(
    <QueryClientProvider client={client()}>
      <VersionBar workspaceId="ws-1" git path={path} revision={0} {...props} />
    </QueryClientProvider>,
  );
  return props;
};

describe("мастер «Новая версия»", () => {
  beforeAll(async () => {
    await loadPackStudioNamespace();
    await i18n.changeLanguage("ru");
  });
  afterEach(() => {
    vi.restoreAllMocks();
  });

  it("черновик: живой класс, номер мягче минимума, причины ведут в файлы", async () => {
    const props = mountBar(DRAFT);

    expect(await screen.findByTestId("version-class")).toHaveTextContent(
      "minor: новые поля, заготовки подписания",
    );
    expect(screen.getByTestId("version-number")).toHaveTextContent("2026.1.7");
    expect(screen.getByTestId("version-number-fix")).toHaveTextContent(
      "2026.2.0",
    );
    await userEvent.click(screen.getByTestId("version-class"));
    const reasons = screen.getByTestId("version-reasons");
    await userEvent.click(
      within(reasons).getByText(/Новое поле meta_fields\.title_en/),
    );
    expect(props.onOpenFile).toHaveBeenCalledWith(
      `${DRAFT.version.path}/version.yaml`,
    );
  });

  it("номер: класс мягче минимума выбрать нельзя, перенос открывает тот же файл", async () => {
    const moved = fixture(
      PackVersionMovedSchema,
      "PackVersionMoved",
      "renumbered",
    );
    const renumber = vi
      .spyOn(packStudioApi, "renumberVersion")
      .mockResolvedValue(moved);
    const props = mountBar(DRAFT);

    await userEvent.click(await screen.findByTestId("version-renumber-open"));
    expect(screen.getByTestId("version-renumber-patch")).toBeDisabled();
    expect(screen.getByTestId("version-renumber-minor")).toBeChecked();
    await userEvent.click(screen.getByTestId("version-renumber-submit"));

    await waitFor(() => {
      expect(renumber).toHaveBeenCalledWith("ws-1", DRAFT.version, "2026.2.0");
    });
    expect(props.onFilesChanged).toHaveBeenCalled();
    expect(props.onOpenFile).toHaveBeenCalledWith(
      `${moved.version.path}/files/report/main.tex`,
    );
  });

  it("заметки: черновик из отчёта и пары ru и en", async () => {
    const save = vi
      .spyOn(packStudioApi, "saveVersionNotes")
      .mockResolvedValue(DRAFT);
    mountBar(DRAFT);

    await userEvent.click(await screen.findByTestId("version-notes-open"));
    await userEvent.click(screen.getByTestId("version-notes-fill"));
    expect(screen.getByTestId("version-notes-ru")).toHaveValue(
      "Новые поля: «Название работы на английском».",
    );
    await userEvent.type(screen.getByTestId("version-notes-ru"), "\nЕщё");
    expect(screen.getByTestId("version-notes-save")).toBeDisabled();
    await userEvent.type(screen.getByTestId("version-notes-en"), "\nMore");
    await userEvent.click(screen.getByTestId("version-notes-save"));

    await waitFor(() => {
      expect(save).toHaveBeenCalledWith("ws-1", DRAFT.version, {
        changes: {
          ru: ["Новые поля: «Название работы на английском».", "Ещё"],
          en: ['New fields: "Title in English".', "More"],
        },
      });
    });
  });

  it("выпуск: номер занят в основной ветке, правки переносятся в следующий", async () => {
    const ready: PackVersionState = {
      ...DRAFT,
      minimum: "patch",
      suggested: "patch",
      number_ok: true,
      changes: { ru: ["Пункт"], en: ["Item"] },
    };
    vi.spyOn(packStudioApi, "releaseVersion").mockRejectedValue(
      apiError("version_taken"),
    );
    const moved = fixture(
      PackVersionMovedSchema,
      "PackVersionMoved",
      "edits_moved",
    );
    const move = vi
      .spyOn(packStudioApi, "moveVersionEdits")
      .mockResolvedValue(moved);
    const props = mountBar(ready);

    await userEvent.click(await screen.findByTestId("version-release-open"));
    await userEvent.click(screen.getByTestId("version-release-submit"));
    await userEvent.click(await screen.findByTestId("version-release-move"));

    await waitFor(() => {
      expect(move).toHaveBeenCalledWith("ws-1", ready.version, "2026.1.8");
    });
    expect(props.onOpenFile).toHaveBeenCalledWith(
      `${moved.version.path}/files/report/main.tex`,
    );
  });

  it("выпуск: класс и галочка версии по умолчанию уходят на сервер", async () => {
    const ready: PackVersionState = {
      ...DRAFT,
      minimum: "patch",
      suggested: "patch",
      number_ok: true,
      changes: { ru: ["Пункт"], en: ["Item"] },
    };
    const release = vi
      .spyOn(packStudioApi, "releaseVersion")
      .mockResolvedValue(fixture(PackReleaseSchema, "PackRelease", "released"));
    const props = mountBar(ready);

    await userEvent.click(await screen.findByTestId("version-release-open"));
    await userEvent.click(screen.getByTestId("version-release-default"));
    await userEvent.click(screen.getByTestId("version-release-submit"));

    await waitFor(() => {
      expect(release).toHaveBeenCalledWith("ws-1", ready.version, {
        kind: "patch",
        set_default: false,
      });
    });
    expect(props.onFilesChanged).toHaveBeenCalled();
  });

  it("выпущенная версия, правленная мимо Студии: «Перенести правки»", async () => {
    const moved = fixture(
      PackVersionMovedSchema,
      "PackVersionMoved",
      "edits_moved",
    );
    const move = vi
      .spyOn(packStudioApi, "moveVersionEdits")
      .mockResolvedValue(moved);
    const props = mountBar(RELEASED, `${RELEASED.version.path}/version.yaml`);

    await userEvent.click(await screen.findByTestId("version-move-open"));
    await userEvent.click(screen.getByTestId("version-move-submit"));

    await waitFor(() => {
      expect(move).toHaveBeenCalledWith("ws-1", RELEASED.version, "2026.1.8");
    });
    expect(props.onOpenFile).toHaveBeenCalledWith(
      `${moved.version.path}/version.yaml`,
    );
  });

  it("шаг 1: база по умолчанию последняя выпущенная, класс даёт номер", async () => {
    vi.spyOn(packStudioApi, "versionOptions").mockResolvedValue(
      fixture(PackVersionOptionsSchema, "PackVersionOptions", "coursework"),
    );
    const created = fixture(
      PackVersionCreatedSchema,
      "PackVersionCreated",
      "patch",
    );
    const create = vi
      .spyOn(packStudioApi, "createVersion")
      .mockResolvedValue(created);
    const onCreated = vi.fn();
    render(
      <QueryClientProvider client={client()}>
        <NewVersionDialog
          workspaceId="ws-1"
          target={{ pack: "hse-cs-sse", template: "coursework" }}
          onClose={vi.fn()}
          onCreated={onCreated}
        />
      </QueryClientProvider>,
    );

    await userEvent.click(await screen.findByTestId("new-version-class-minor"));
    expect(screen.getByTestId("new-version-submit")).toHaveTextContent(
      "2026.2.0",
    );
    await userEvent.click(screen.getByTestId("new-version-submit"));

    await waitFor(() => {
      expect(create).toHaveBeenCalledWith("ws-1", "hse-cs-sse", "coursework", {
        base: "2026.1.6",
        update_class: "minor",
      });
    });
    expect(onCreated).toHaveBeenCalledWith(created);
  });
});
