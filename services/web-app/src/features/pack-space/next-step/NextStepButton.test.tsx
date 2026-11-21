import {
  cleanup,
  render,
  screen,
  waitFor,
  within,
} from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
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
import { packStudioApi, type PackVersionCreated } from "@entities/pack-studio";
import { ApiError } from "@shared/api";
import { i18n } from "@shared/lib";
import { loadPackOutcomeNamespace } from "@shared/lib/i18n/packOutcomeNamespace";
import { loadPackSpaceNamespace } from "@shared/lib/i18n/packSpaceNamespace";
import { loadPackStudioNamespace } from "@shared/lib/i18n/packStudioNamespace";
import { SpaceProvider } from "../context/SpaceContext";
import { GALLERY_REF, GALLERY_TREE, GALLERY_WORKSPACE } from "../galleryKit";
import { SpaceScreen } from "../shell/SpaceScreen";
import { versionStateOf } from "./fixtures";
import {
  SENT,
  SLOTS,
  V,
  ciOf,
  gitOf,
  lintOf,
  location,
  mount,
} from "./nextStepTestKit";
import { SPACE_BASE } from "../spaceTestKit";

// Главная кнопка полосы пространства в сборе: статус изменений читается из подменённого API, а
// не подаётся готовым (сам выбор шага проверяет `resolveNextStep.test.ts`).
vi.setConfig({ testTimeout: 30_000 });

const step = (): Promise<HTMLElement> =>
  screen.findByTestId("sp-next-step", undefined, { timeout: 15000 });

const created = (version: string): PackVersionCreated => ({
  version: {
    pack: "hse-cs-sse",
    template: "coursework",
    version,
    path: `hse-cs-sse/templates/coursework/versions/${version}`,
  },
  base: "2026.1.2",
  update_class: "patch",
  warnings: [],
});

const EMPTY = { changed: [], uncommitted: [], dirty: false };

describe("главная кнопка", () => {
  beforeAll(async () => {
    await Promise.all([
      loadPackSpaceNamespace(),
      loadPackStudioNamespace(),
      loadPackOutcomeNamespace(),
    ]);
    await i18n.changeLanguage("ru");
  });
  beforeEach(() => {
    window.localStorage.clear();
  });
  afterEach(() => {
    cleanup();
    vi.restoreAllMocks();
  });

  it("выпущенная версия без правок: «Править копию» создаёт версию без окна и остаётся на экране", async () => {
    const create = vi
      .spyOn(packStudioApi, "createVersion")
      .mockResolvedValue(created("2026.1.3"));
    mount({
      git: gitOf(EMPTY),
      url: `${SPACE_BASE}/2026.1.2/result?sel=documents%3Ats&i.kind=research`,
    });
    const button = await step();
    await waitFor(() => {
      expect(button).toHaveTextContent("Править копию");
    });
    expect(button).toHaveClass("primary");
    await userEvent.click(button);
    await waitFor(() => {
      expect(create).toHaveBeenCalledTimes(1);
    });
    // Без окна выбора класса: сразу «небольшая правка» от открытой версии.
    expect(create).toHaveBeenCalledWith(
      "gallery-ws",
      "hse-cs-sse",
      "coursework",
      {
        base: "2026.1.2",
        update_class: "patch",
      },
    );
    expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
    await waitFor(() => {
      expect(location()).toContain("/2026.1.3/result");
    });
    // Тот же выбранный элемент и те же условия студента.
    expect(location()).toContain("sel=documents%3Ats");
    expect(location()).toContain("i.kind=research");
  });

  it("номер занят в основной ветке: берётся свободный, который подсказал сервер", async () => {
    const create = vi
      .spyOn(packStudioApi, "createVersion")
      .mockRejectedValueOnce(
        new ApiError("занят", "version_taken", 409, { suggested: "2026.1.3" }),
      )
      .mockResolvedValueOnce(created("2026.1.3"));
    mount({
      git: gitOf(EMPTY),
      url: `${SPACE_BASE}/2026.1.2/result`,
    });
    await userEvent.click(await step());
    await waitFor(() => {
      expect(create).toHaveBeenCalledTimes(2);
    });
    expect(create.mock.calls[1]?.[3]).toEqual({
      base: "2026.1.2",
      version: "2026.1.3",
    });
    await waitFor(() => {
      expect(location()).toContain("/2026.1.3/");
    });
  });

  it("правки в «Содержимом» переезжают на копию: тот же документ и файл", async () => {
    vi.spyOn(packStudioApi, "createVersion").mockResolvedValue(
      created("2026.1.3"),
    );
    const base = "hse-cs-sse/templates/coursework/versions/2026.1.2";
    mount({
      git: gitOf(EMPTY),
      url: `${SPACE_BASE}/2026.1.2/content?doc=ts&seg=text&file=${encodeURIComponent(`${base}/files/ts/ts.ru.tex`)}`,
    });
    await userEvent.click(await step());
    await waitFor(() => {
      expect(location()).toContain("/2026.1.3/content");
    });
    expect(location()).toContain("doc=ts");
    expect(location()).toContain("seg=text");
    expect(decodeURIComponent(location())).toContain(
      "versions/2026.1.3/files/ts/ts.ru.tex",
    );
  });

  it("ссылка из старого вида (copy=1): копию не создаём сами, ставим фокус на кнопку", async () => {
    const create = vi.spyOn(packStudioApi, "createVersion");
    mount({
      git: gitOf(EMPTY),
      url: `${SPACE_BASE}/2026.1.2/result?copy=1`,
    });
    const button = await step();
    await waitFor(() => {
      expect(button).toHaveFocus();
    });
    expect(location()).not.toContain("copy=");
    expect(create).not.toHaveBeenCalled();
  });

  it("выпущенная версия, правки в другой: «К моему черновику», переход к нему", async () => {
    mount({ url: `${SPACE_BASE}/2026.1.2/result` });
    const button = await step();
    await waitFor(() => {
      expect(button).toHaveTextContent("К моему черновику 2026.1.3");
    });
    await userEvent.click(button);
    await waitFor(() => {
      expect(location()).toContain("/2026.1.3/result");
    });
  });

  it("ошибки проверки: «Исправить ошибки · N» ведёт в «Проверку», «Замечания»", async () => {
    mount({
      lint: lintOf([
        {
          severity: "error",
          check: "schema",
          message: "нет поля",
          path: `${V}/files/technical_specification/doc.yaml`,
          line: 6,
          pointer: null,
        },
      ]),
      url: `${SPACE_BASE}/2026.1.3/result?changes=1`,
    });
    const button = await screen.findByRole(
      "button",
      { name: /Исправить ошибки · 1/ },
      { timeout: 15000 },
    );
    await userEvent.click(button);
    expect(location()).toContain("/check");
    expect(location()).toContain("part=issues");
    expect(location()).not.toContain("changes=1");
  });

  it("нет заметок: «Описать изменения» открывает панель и ставит фокус на поле заметок", async () => {
    vi.spyOn(packStudioApi, "versionState").mockResolvedValue(versionStateOf());
    mount({
      notes: false,
      url: `${SPACE_BASE}/2026.1.3/result`,
    });
    const button = await screen.findByRole(
      "button",
      { name: "Описать изменения" },
      { timeout: 15000 },
    );
    await userEvent.click(button);
    expect(location()).toContain("changes=1");
    const field = await screen.findByTestId("sp-sb-notes-ru", undefined, {
      timeout: 15000,
    });
    await waitFor(() => {
      expect(field).toHaveFocus();
    });
    // Подсказка про фокус из адреса убирается: она нужна один раз.
    await waitFor(() => {
      expect(location()).not.toContain("focus=");
    });
  });

  it("всё готово: «Отправить на рассмотрение» открывает панель с кнопкой подтверждения", async () => {
    mount({ url: `${SPACE_BASE}/2026.1.3/result` });
    const button = await screen.findByRole(
      "button",
      { name: "Отправить на рассмотрение" },
      { timeout: 15000 },
    );
    expect(button).toHaveClass("primary");
    await userEvent.click(button);
    const confirm = await screen.findByTestId("sp-sb-primary", undefined, {
      timeout: 15000,
    });
    await waitFor(() => {
      expect(confirm).toHaveFocus();
    });
    // От «Описать изменения» до открытого запроса: одна кнопка подтверждения внутри панели.
    expect(
      screen.getAllByRole("button", { name: "Отправить на рассмотрение" }),
    ).toHaveLength(2);
  });

  it("запрос открыт: вторичная кнопка со статусом проверок, открывает панель", async () => {
    mount({
      git: gitOf(SENT),
      ci: ciOf(),
      url: `${SPACE_BASE}/2026.1.3/result`,
    });
    const button = await screen.findByRole(
      "button",
      { name: /Запрос #412 · проверки идут/ },
      { timeout: 15000 },
    );
    expect(button).not.toHaveClass("primary");
    await userEvent.click(button);
    expect(location()).toContain("changes=1");
  });

  it("запрос открыт, есть новые правки: «Обновить запрос»", async () => {
    mount({
      git: gitOf({ ...SENT, dirty: true, head_sha: "bbb" }),
      url: `${SPACE_BASE}/2026.1.3/result`,
    });
    expect(
      await screen.findByRole(
        "button",
        { name: "Обновить запрос" },
        { timeout: 15000 },
      ),
    ).toHaveClass("primary");
  });

  it("запрос принят: «Начать новую правку» сбрасывает на свежую основную ветку после подтверждения", async () => {
    const reset = vi
      .spyOn(packStudioApi, "startOver")
      .mockResolvedValue(gitOf({ ...EMPTY, workspace: GALLERY_WORKSPACE }));
    mount({
      git: gitOf({ ...SENT, dirty: false }),
      ci: ciOf({ state: "success", pr_state: "merged" }),
      url: `${SPACE_BASE}/2026.1.3/result`,
    });
    await userEvent.click(
      await screen.findByRole(
        "button",
        { name: "Начать новую правку" },
        { timeout: 15000 },
      ),
    );
    const dialog = await screen.findByRole("dialog", undefined, {
      timeout: 15000,
    });
    expect(reset).not.toHaveBeenCalled();
    await userEvent.click(
      await within(dialog).findByTestId("git-start-over-submit"),
    );
    await waitFor(() => {
      expect(reset).toHaveBeenCalledWith("gallery-ws", false);
    });
  });

  it("пока git читается, кнопки нет", async () => {
    vi.spyOn(packStudioApi, "git").mockReturnValue(
      new Promise(() => undefined),
    );
    vi.spyOn(packStudioApi, "tree").mockResolvedValue(GALLERY_TREE);
    const client = new QueryClient();
    render(
      <MemoryRouter initialEntries={[`${SPACE_BASE}/2026.1.2/result`]}>
        <QueryClientProvider client={client}>
          <SpaceProvider
            workspace={GALLERY_WORKSPACE}
            tree={GALLERY_TREE}
            versionRef={{ ...GALLERY_REF, version: "2026.1.2" }}
            tab="result"
          >
            <SpaceScreen slots={SLOTS} phone={false} />
          </SpaceProvider>
        </QueryClientProvider>
      </MemoryRouter>,
    );
    await screen.findByTestId("sp-changes-button");
    expect(screen.queryByTestId("sp-next-step")).not.toBeInTheDocument();
  });
});

describe("главная кнопка: папка и подключение", () => {
  beforeAll(async () => {
    await loadPackSpaceNamespace();
    await i18n.changeLanguage("ru");
  });
  afterEach(() => {
    cleanup();
    vi.restoreAllMocks();
  });

  const mountWith = (workspace: typeof GALLERY_WORKSPACE) => {
    render(
      <MemoryRouter initialEntries={[`${SPACE_BASE}/2026.1.2/result`]}>
        <QueryClientProvider client={new QueryClient()}>
          <SpaceProvider
            workspace={workspace}
            tree={GALLERY_TREE}
            versionRef={{ ...GALLERY_REF, version: "2026.1.2" }}
            tab="result"
          >
            <SpaceScreen slots={SLOTS} phone={false} />
          </SpaceProvider>
        </QueryClientProvider>
      </MemoryRouter>,
    );
  };

  it("папка на диске: главной кнопки нет, чип «Записано в папку»", async () => {
    mountWith({ ...GALLERY_WORKSPACE, kind: "folder", folder: "/x/packs" });
    const chip = await screen.findByTestId("sp-next-step");
    expect(chip).toHaveTextContent("Записано в папку");
    expect(chip.tagName).not.toBe("BUTTON");
  });

  it("пространство подключается: подпись «Подключаем…», кнопки нет", async () => {
    mountWith({ ...GALLERY_WORKSPACE, state: "cloning" });
    const note = await screen.findByTestId("sp-next-step");
    expect(note).toHaveTextContent("Подключаем…");
    expect(note.tagName).not.toBe("BUTTON");
  });

  it("подключение не удалось: «Проверить доступ» открывает окно доступа к репозиторию", async () => {
    mountWith({
      ...GALLERY_WORKSPACE,
      state: "failed",
      error: { code: "workspace_git_failed", detail: "нет доступа" },
    });
    await userEvent.click(
      await screen.findByRole("button", { name: "Проверить доступ" }),
    );
    expect(await screen.findByRole("dialog")).toBeInTheDocument();
  });
});
