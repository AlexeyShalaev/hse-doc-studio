import { readFileSync } from "node:fs";
import { join } from "node:path";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router";
import {
  afterEach,
  beforeAll,
  beforeEach,
  describe,
  expect,
  it,
  vi,
} from "vitest";
import { gitRemoteApi } from "@entities/git-remote";
import {
  CatalogApplySchema,
  CatalogCheckSchema,
  CatalogEventListSchema,
  CatalogOverviewSchema,
  CatalogSourceSchema,
  packCatalogApi,
} from "@entities/pack-catalog";
import { packStudioApi } from "@entities/pack-studio";
import { ApiError } from "@shared/api";
import { i18n, loadAdminNamespaces } from "@shared/lib";
import { PackCatalogAdminPage } from "./PackCatalogAdminPage";

const FIXTURES = join(
  import.meta.dirname,
  "../../../../../../contracts/pack-catalog/fixtures",
);
const load = (dir: string, name: string): unknown =>
  JSON.parse(readFileSync(join(FIXTURES, dir, `${name}.json`), "utf8"));

const OVERVIEW = CatalogOverviewSchema.parse(
  load("CatalogOverview", "with_sources"),
);
const EMPTY = CatalogOverviewSchema.parse(load("CatalogOverview", "empty"));
const CHECK_OK = CatalogCheckSchema.parse(load("CatalogCheck", "ok"));
const APPLIED = CatalogApplySchema.parse(load("CatalogApply", "applied"));
const GIT = CatalogSourceSchema.parse(load("CatalogSource", "git_applied"));
const ARCHIVE = CatalogSourceSchema.parse(
  load("CatalogSource", "archive_failed"),
);
const HISTORY = CatalogEventListSchema.parse(
  load("CatalogEventList", "history"),
);

const mount = () =>
  render(
    <QueryClientProvider
      client={
        new QueryClient({ defaultOptions: { queries: { retry: false } } })
      }
    >
      <MemoryRouter>
        <PackCatalogAdminPage />
      </MemoryRouter>
    </QueryClientProvider>,
  );

const openMenu = async (sourceId: string) => {
  const card = await screen.findByTestId(`pc-source-${sourceId}`);
  await userEvent.click(within(card).getByTestId("pc-source-menu"));
};

describe("админка: каталоги паков", () => {
  beforeAll(async () => {
    await loadAdminNamespaces(["packCatalog"]);
    await i18n.changeLanguage("ru");
  });
  beforeEach(() => {
    vi.spyOn(gitRemoteApi, "listCredentials").mockResolvedValue([]);
    vi.spyOn(packStudioApi, "serviceAccess").mockResolvedValue([]);
  });
  afterEach(() => {
    vi.restoreAllMocks();
  });

  it("источники с состоянием, ошибкой и паками, другие паки только для чтения", async () => {
    vi.spyOn(packCatalogApi, "overview").mockResolvedValue(OVERVIEW);
    mount();
    const git = await screen.findByTestId(`pc-source-${GIT.id}`);
    expect(within(git).getByText("acme-packs")).toBeInTheDocument();
    expect(within(git).getByTestId("pc-source-location")).toHaveTextContent(
      "https://git.example.org/acme/packs.git @ v2026.1.1",
    );
    expect(within(git).getByTestId("pc-source-status")).toHaveTextContent(
      "Всё подключено",
    );
    expect(within(git).getByText("Обновляется сам")).toBeInTheDocument();
    expect(within(git).getByTestId("pc-source-applied")).toHaveTextContent(
      "Сейчас подключено: 4b825dc6",
    );
    expect(within(git).getByText("thesis 2026.1.0")).toBeInTheDocument();

    const archive = screen.getByTestId(`pc-source-${ARCHIVE.id}`);
    expect(within(archive).getByText("Архив")).toBeInTheDocument();
    expect(within(archive).getByTestId("pc-source-location")).toHaveTextContent(
      "packs-2026.zip",
    );
    expect(
      within(archive).getByText(
        "В архиве есть ссылки, абсолютные пути или выход за его папку. Такой архив не принимается.",
      ),
    ).toBeInTheDocument();
    expect(
      within(archive).getByText("Ещё не подключён: проверьте и примените"),
    ).toBeInTheDocument();
    expect(within(archive).getByTestId("pc-source-status")).toHaveTextContent(
      "Не удалось проверить",
    );
    expect(within(archive).getByText("Подробнее")).toBeInTheDocument();

    const others = screen.getByTestId("pc-others");
    expect(within(others).getByText("Встроенный")).toBeInTheDocument();
    expect(
      within(others).getByText("Из удалённого источника"),
    ).toBeInTheDocument();
    expect(within(others).getByText("Скрыт из мастера")).toBeInTheDocument();
  });

  it("«Проверить» показывает отчёт, «Применить» отправляет проверенную ревизию", async () => {
    vi.spyOn(packCatalogApi, "overview").mockResolvedValue(OVERVIEW);
    const check = vi.spyOn(packCatalogApi, "check").mockResolvedValue(CHECK_OK);
    const apply = vi.spyOn(packCatalogApi, "apply").mockResolvedValue(APPLIED);
    mount();
    const git = await screen.findByTestId(`pc-source-${GIT.id}`);
    await userEvent.click(within(git).getByTestId("pc-source-check"));
    expect(check).toHaveBeenCalledTimes(1);
    expect(check).toHaveBeenCalledWith(GIT.id);
    expect(
      await screen.findByText("Можно применить: появятся 2 версии."),
    ).toBeInTheDocument();
    await userEvent.click(screen.getByTestId("pc-apply"));
    expect(apply).toHaveBeenCalledWith(GIT.id, CHECK_OK.revision);
    expect(await screen.findByTestId("catalog-apply-result")).toHaveTextContent(
      "acme-thesis/thesis@2026.1.1",
    );
  });

  it("источник изменился после проверки: предлагает проверить снова", async () => {
    vi.spyOn(packCatalogApi, "overview").mockResolvedValue(OVERVIEW);
    const check = vi.spyOn(packCatalogApi, "check").mockResolvedValue(CHECK_OK);
    vi.spyOn(packCatalogApi, "apply").mockRejectedValue(
      new ApiError("moved", "revision_moved", 409, {
        expected: "a",
        actual: "b",
      }),
    );
    mount();
    const git = await screen.findByTestId(`pc-source-${GIT.id}`);
    await userEvent.click(within(git).getByTestId("pc-source-check"));
    await userEvent.click(await screen.findByTestId("pc-apply"));
    expect(
      await screen.findByText(/Источник изменился после проверки/),
    ).toBeInTheDocument();
    await userEvent.click(screen.getByTestId("catalog-recheck"));
    await waitFor(() => {
      expect(check).toHaveBeenCalledTimes(2);
    });
  });

  it("препятствия запрещают «Применить»", async () => {
    vi.spyOn(packCatalogApi, "overview").mockResolvedValue(OVERVIEW);
    vi.spyOn(packCatalogApi, "check").mockResolvedValue(
      CatalogCheckSchema.parse(load("CatalogCheck", "blocked")),
    );
    mount();
    const git = await screen.findByTestId(`pc-source-${GIT.id}`);
    await userEvent.click(within(git).getByTestId("pc-source-check"));
    expect(await screen.findByText("Применить нельзя:")).toBeInTheDocument();
    expect(screen.getByTestId("pc-apply")).toBeDisabled();
  });

  it("выключение и удаление источника, история событий", async () => {
    vi.spyOn(packCatalogApi, "overview").mockResolvedValue(OVERVIEW);
    const update = vi
      .spyOn(packCatalogApi, "update")
      .mockResolvedValue({ ...GIT, enabled: false });
    const remove = vi.spyOn(packCatalogApi, "remove").mockResolvedValue();
    vi.spyOn(packCatalogApi, "history").mockResolvedValue(HISTORY);
    mount();

    await openMenu(GIT.id);
    await userEvent.click(await screen.findByTestId("pc-source-toggle"));
    expect(update).toHaveBeenCalledWith(GIT.id, { enabled: false });

    await openMenu(GIT.id);
    await userEvent.click(await screen.findByTestId("pc-source-history"));
    const history = await screen.findByTestId("pc-history");
    expect(within(history).getByText("Применение")).toBeInTheDocument();
    expect(
      within(history).getByText(
        "В репозитории нет такого тега, ветки или коммита.",
      ),
    ).toBeInTheDocument();
    await userEvent.keyboard("{Escape}");

    await openMenu(GIT.id);
    await userEvent.click(await screen.findByTestId("pc-source-remove"));
    expect(
      await screen.findByText(/Версии останутся в хранилище/),
    ).toBeInTheDocument();
    await userEvent.click(screen.getByTestId("pc-remove-confirm"));
    expect(remove).toHaveBeenCalledWith(GIT.id);
  });

  it("добавление git: тело запроса из формы, затем сразу проверка", async () => {
    vi.spyOn(packCatalogApi, "overview").mockResolvedValue(EMPTY);
    const addGit = vi.spyOn(packCatalogApi, "addGit").mockResolvedValue(GIT);
    const check = vi.spyOn(packCatalogApi, "check").mockResolvedValue(CHECK_OK);
    mount();
    expect(await screen.findByTestId("pc-sources-empty")).toBeInTheDocument();
    await userEvent.click(screen.getByTestId("pc-add-open"));
    await userEvent.type(
      screen.getByTestId("pc-add-url"),
      "https://github.com/acme/packs",
    );
    await userEvent.type(screen.getByTestId("pc-add-ref"), "v2026.1.1");
    await userEvent.click(screen.getByTestId("pc-add-track"));
    await userEvent.click(screen.getByTestId("pc-add-submit"));
    expect(addGit).toHaveBeenCalledWith({
      url: "https://github.com/acme/packs",
      packs_path: "packs",
      ref: "v2026.1.1",
      replace_builtin: false,
      track: true,
    });
    await waitFor(() => {
      expect(check).toHaveBeenCalledWith(GIT.id);
    });
  });

  it("добавление архива: файл телом, поля строкой запроса, предел размера виден", async () => {
    vi.spyOn(packCatalogApi, "overview").mockResolvedValue(EMPTY);
    const addArchive = vi
      .spyOn(packCatalogApi, "addArchive")
      .mockResolvedValue(ARCHIVE);
    vi.spyOn(packCatalogApi, "check").mockResolvedValue(CHECK_OK);
    mount();
    await userEvent.click(await screen.findByTestId("pc-add-open"));
    await userEvent.click(screen.getByRole("button", { name: "Архив" }));
    expect(screen.getByText(/Не больше 100/)).toBeInTheDocument();
    const file = new File(["zip"], "packs-2026.zip", {
      type: "application/zip",
    });
    await userEvent.upload(screen.getByTestId("pc-archive-input"), file);
    await userEvent.type(screen.getByTestId("pc-add-label"), "Паки кафедры");
    await userEvent.click(screen.getByTestId("pc-add-submit"));
    expect(addArchive).toHaveBeenCalledWith(file, {
      name: "packs-2026.zip",
      label: "Паки кафедры",
      packsPath: "",
      replaceBuiltin: false,
    });
  });

  it("файл не архив: отправить нельзя", async () => {
    vi.spyOn(packCatalogApi, "overview").mockResolvedValue(EMPTY);
    mount();
    await userEvent.click(await screen.findByTestId("pc-add-open"));
    await userEvent.click(screen.getByRole("button", { name: "Архив" }));
    // Перетаскивание не смотрит на accept: проверяет само окно.
    await userEvent
      .setup({ applyAccept: false })
      .upload(
        screen.getByTestId("pc-archive-input"),
        new File(["x"], "packs.rar"),
      );
    expect(
      screen.getByText("Нужен архив .zip или .tar.gz."),
    ).toBeInTheDocument();
    expect(screen.getByTestId("pc-add-submit")).toBeDisabled();
  });
});
