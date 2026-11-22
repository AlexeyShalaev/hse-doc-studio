import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { MemoryRouter, Route, Routes, useLocation } from "react-router";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { ApiError } from "@shared/api";
import {
  packStudioApi,
  packStudioKeys,
  type PackTree,
  type PackWorkspace,
} from "@entities/pack-studio";
import {
  GALLERY_TREE,
  GALLERY_WORKSPACE,
} from "@features/pack-space/galleryKit";
import { PackStudioApp } from "./PackStudioApp";

// Каркас и редкие экраны тяжёлые: здесь важно, кто и когда открывается.
vi.mock("@widgets/AppTitlebar", () => ({ AppTitlebar: () => null }));
vi.mock("@widgets/AppStatusBar", () => ({ AppStatusBar: () => null }));
vi.mock("./WorkspacesScreen", () => ({
  WorkspacesScreen: () => <div data-testid="ws-list" />,
}));

const WS = GALLERY_WORKSPACE.id;
const BASE = `/pack-studio/w/${WS}`;
const T = `${BASE}/t/hse-cs-sse/coursework`;
// Версия по умолчанию дерева-фикстуры (выпущенная) и черновик.
const DEFAULT = `${T}/2026.1.2`;
const DRAFT = `${T}/2026.1.3`;

const Probe = () => {
  const { pathname, search } = useLocation();
  return <output data-testid="location">{`${pathname}${search}`}</output>;
};

const open = (
  url: string,
  options: { workspace?: Partial<PackWorkspace>; tree?: PackTree } = {},
) => {
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false, staleTime: Infinity } },
  });
  client.setQueryData(packStudioKeys.workspace(WS), {
    ...GALLERY_WORKSPACE,
    ...options.workspace,
  });
  client.setQueryData(packStudioKeys.tree(WS), options.tree ?? GALLERY_TREE);
  render(
    <QueryClientProvider client={client}>
      <MemoryRouter initialEntries={[url]}>
        <Routes>
          <Route path="/pack-studio/*" element={<PackStudioApp />} />
        </Routes>
        <Probe />
      </MemoryRouter>
    </QueryClientProvider>,
  );
};

const where = () => screen.getByTestId("location").textContent;
const shell = () => screen.findByTestId("sp-shell");

describe("маршруты Студии шаблонов", () => {
  beforeEach(() => {
    window.localStorage.clear();
  });
  afterEach(() => {
    cleanup();
  });

  describe("адреса из раздела 4.2 открывают пространство без флагов", () => {
    it("список пространств", async () => {
      open("/pack-studio");
      expect(await screen.findByTestId("ws-list")).toBeInTheDocument();
      expect(screen.queryByTestId("sp-shell")).toBeNull();
    });

    it.each([
      ["result", `${DRAFT}/result`],
      ["content", `${DRAFT}/content`],
      ["check", `${DRAFT}/check`],
    ])("вкладка %s: название пространства и три вкладки", async (tab, url) => {
      open(url);
      await shell();
      expect(screen.getByTestId("sp-ws-name")).toHaveTextContent(
        GALLERY_WORKSPACE.label,
      );
      expect(screen.getByTestId(`sp-tab-${tab}`)).toHaveAttribute(
        "aria-current",
        "page",
      );
      expect(
        screen.getAllByRole("link", { name: /Результат|Содержимое|Проверка/ }),
      ).toHaveLength(3);
    });

    it("корень пространства: перенаправление на версию по умолчанию", async () => {
      open(BASE);
      await shell();
      expect(where()).toBe(`${DEFAULT}/result`);
    });

    it("переключение вкладок меняет адрес", async () => {
      open(`${DRAFT}/result?i.kind=research`);
      await shell();
      // Вкладка «Содержимое» грузится лениво: переход завершается после загрузки её чанка.
      fireEvent.click(screen.getByTestId("sp-tab-content"));
      await vi.waitFor(() => {
        expect(where()).toBe(`${DRAFT}/content?i.kind=research`);
      });
      fireEvent.click(screen.getByTestId("sp-tab-check"));
      await vi.waitFor(() => {
        expect(where()).toBe(`${DRAFT}/check?i.kind=research`);
      });
    });

    it("версия без вкладки и неизвестная вкладка ведут на «Результат», query остаётся", async () => {
      open(`${DRAFT}?i.kind=research`);
      await shell();
      expect(where()).toBe(`${DRAFT}/result?i.kind=research`);
      cleanup();
      open(`${DRAFT}/files`);
      await shell();
      expect(where()).toBe(`${DRAFT}/result`);
    });

    it("версии нет в дереве: вход подбирает место сам", async () => {
      open(`${T}/0.0.1/result?i.kind=research`);
      await shell();
      expect(where()).toBe(`${DEFAULT}/result?i.kind=research`);
    });

    it("неизвестный адрес под /pack-studio ведёт в список", async () => {
      open("/pack-studio/nope/deeper");
      expect(await screen.findByTestId("ws-list")).toBeInTheDocument();
      expect(where()).toBe("/pack-studio");
    });
  });

  describe("флаг ?ux= из 0.38.0 больше ничего не значит", () => {
    it.each([
      [`${DRAFT}/result?ux=2`, `${DRAFT}/result`],
      [`${DRAFT}/check?ux=1&i.kind=research`, `${DRAFT}/check?i.kind=research`],
      [`${BASE}?ux=2`, `${DEFAULT}/result`],
      [`${BASE}?ux=1`, `${DEFAULT}/result`],
    ])("%s -> %s", async (from, to) => {
      open(from);
      await shell();
      expect(where()).toBe(to);
    });

    it("на списке пространств тоже убирается", async () => {
      open("/pack-studio?ux=1");
      expect(await screen.findByTestId("ws-list")).toBeInTheDocument();
      expect(where()).toBe("/pack-studio");
    });

    it("память флага в браузере стирается и на вид не влияет", async () => {
      window.localStorage.setItem("ps.ux", "1");
      open(`${DRAFT}/result`);
      await shell();
      expect(window.localStorage.getItem("ps.ux")).toBeNull();
    });
  });

  describe("старые адреса прежнего вида перенаправляются", () => {
    const FILE = encodeURIComponent(
      "hse-cs-sse/templates/coursework/versions/2026.1.3/version.yaml",
    );
    it.each([
      [`${BASE}/result/hse-cs-sse/coursework/2026.1.3`, `${DRAFT}/result`],
      [
        `${BASE}/result/hse-cs-sse/coursework/2026.1.3?selected=documents%3Ats&i.kind=research&scenario=c1`,
        `${DRAFT}/result?sel=documents%3Ats&i.kind=research&case=c1`,
      ],
      [
        `${BASE}/result/hse-cs-sse/coursework/2026.1.3?view=atlas`,
        `${DRAFT}/check?part=map`,
      ],
      [
        `${BASE}/result/hse-cs-sse/coursework/2026.1.3?view=matrix`,
        `${DRAFT}/check?part=cases`,
      ],
      [
        `${BASE}/result/hse-cs-sse/coursework/2026.1.3?view=lint`,
        `${DRAFT}/check?part=issues`,
      ],
      [`${BASE}/result`, `${DEFAULT}/result`],
      [`${BASE}?file=${FILE}`, `${DRAFT}/content?file=${FILE}`],
      [`${BASE}?view=files`, `${DEFAULT}/content?part=files`],
      [
        `${BASE}?view=files&newVersion=hse-cs-sse%2Fcoursework`,
        `${DEFAULT}/result?copy=1`,
      ],
      [
        `${BASE}/result/hse-cs-sse/coursework/2026.1.3?ux=2&view=compare`,
        `${DRAFT}/check?compare=1`,
      ],
    ])("%s", async (from, to) => {
      open(from);
      await shell();
      expect(where()).toBe(to);
    });

    it("память последнего места: вход в корень возвращает версию, вкладку и условия", async () => {
      open(`${DRAFT}/check?i.kind=research`);
      await shell();
      cleanup();
      open(BASE);
      await shell();
      expect(where()).toBe(`${DRAFT}/check?i.kind=research`);
    });
  });

  describe("особые состояния", () => {
    it("пространство клонируется: сообщение вместо оболочки", async () => {
      open(`${DRAFT}/result`, {
        workspace: { state: "cloning", busy: true },
      });
      expect(await screen.findByTestId("ws-cloning")).toBeInTheDocument();
      expect(screen.queryByTestId("sp-shell")).toBeNull();
    });

    it("нет такого пространства: понятный экран со ссылкой в список", async () => {
      const spy = vi
        .spyOn(packStudioApi, "workspace")
        .mockRejectedValue(
          new ApiError("Request failed with status code 422", "x", 422),
        );
      const client = new QueryClient({
        defaultOptions: { queries: { retry: false } },
      });
      render(
        <QueryClientProvider client={client}>
          <MemoryRouter initialEntries={["/pack-studio/w/nope"]}>
            <Routes>
              <Route path="/pack-studio/*" element={<PackStudioApp />} />
            </Routes>
          </MemoryRouter>
        </QueryClientProvider>,
      );
      const missing = await screen.findByTestId("space-not-found");
      expect(missing).toHaveTextContent("Пространство не найдено");
      expect(missing).not.toHaveTextContent("Request failed");
      expect(
        screen.getByRole("link", { name: "К списку пространств" }),
      ).toHaveAttribute("href", "/pack-studio");
      spy.mockRestore();
    });

    it("в пространстве нет версий: объяснение и возврат к списку", async () => {
      open(BASE, { tree: { ...GALLERY_TREE, packs: [] } });
      expect(
        await screen.findByTestId("space-no-versions"),
      ).toBeInTheDocument();
    });
  });
});
