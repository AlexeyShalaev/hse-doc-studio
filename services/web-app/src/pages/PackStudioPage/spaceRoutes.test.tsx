import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { MemoryRouter, Route, Routes, useLocation } from "react-router";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import {
  packStudioKeys,
  resetPackStudioUx,
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
  WorkspacesScreen: () => <div data-testid="old-list" />,
}));
vi.mock("./WorkspaceEntry", () => ({
  WorkspaceEntry: () => <div data-testid="old-entry" />,
}));
vi.mock("./OutcomeRoute", () => ({
  OutcomeEntry: () => <div data-testid="old-outcome-entry" />,
  OutcomeRoute: () => <div data-testid="old-outcome" />,
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

describe("маршруты Студии шаблонов: флаг ?ux=2", () => {
  beforeEach(() => {
    resetPackStudioUx();
    window.localStorage.clear();
  });
  afterEach(() => {
    cleanup();
    resetPackStudioUx();
  });

  describe("без флага всё как раньше", () => {
    it("список, вход в пространство и «Результат» открывают прежние экраны", async () => {
      open("/pack-studio");
      expect(await screen.findByTestId("old-list")).toBeInTheDocument();
      cleanup();
      open(`${BASE}?file=x`);
      expect(await screen.findByTestId("old-entry")).toBeInTheDocument();
      cleanup();
      open(`${BASE}/result`);
      expect(
        await screen.findByTestId("old-outcome-entry"),
      ).toBeInTheDocument();
      cleanup();
      open(`${BASE}/result/hse-cs-sse/coursework/2026.1.2?i.kind=research`);
      expect(await screen.findByTestId("old-outcome")).toBeInTheDocument();
      expect(screen.queryByTestId("sp-shell")).toBeNull();
      expect(where()).toBe(
        `${BASE}/result/hse-cs-sse/coursework/2026.1.2?i.kind=research`,
      );
    });

    it("новый адрес без флага уходит в список, новый вид не грузится", async () => {
      open(`${DRAFT}/result`);
      expect(await screen.findByTestId("old-list")).toBeInTheDocument();
      expect(where()).toBe("/pack-studio");
    });
  });

  describe("?ux=2: адреса из раздела 4.2 открывают оболочку", () => {
    it.each([
      ["result", `${DRAFT}/result?ux=2`],
      ["content", `${DRAFT}/content?ux=2`],
      ["check", `${DRAFT}/check?ux=2`],
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
      open(`${BASE}?ux=2`);
      await shell();
      expect(where()).toBe(`${DEFAULT}/result?ux=2`);
    });

    it("переключение вкладок меняет адрес", async () => {
      open(`${DRAFT}/result?ux=2&i.kind=research`);
      await shell();
      fireEvent.click(screen.getByTestId("sp-tab-content"));
      expect(where()).toBe(`${DRAFT}/content?i.kind=research`);
      fireEvent.click(screen.getByTestId("sp-tab-check"));
      expect(where()).toBe(`${DRAFT}/check?i.kind=research`);
    });

    it("флаг запоминается: следующий заход без query остаётся в новом виде", async () => {
      open(`${DRAFT}/result?ux=2`);
      await shell();
      cleanup();
      open(`${DRAFT}/result`);
      await shell();
      cleanup();
      open(`${DRAFT}/result?ux=1`);
      expect(await screen.findByTestId("old-list")).toBeInTheDocument();
    });

    it("версия без вкладки и неизвестная вкладка ведут на «Результат», query остаётся", async () => {
      open(`${DRAFT}?ux=2&i.kind=research`);
      await shell();
      expect(where()).toBe(`${DRAFT}/result?ux=2&i.kind=research`);
      cleanup();
      open(`${DRAFT}/files?ux=2`);
      await shell();
      expect(where()).toBe(`${DRAFT}/result?ux=2`);
    });

    it("версии нет в дереве: вход подбирает место сам", async () => {
      open(`${T}/0.0.1/result?ux=2&i.kind=research`);
      await shell();
      expect(where()).toBe(`${DEFAULT}/result?ux=2&i.kind=research`);
    });
  });

  describe("?ux=2: старые адреса перенаправляются", () => {
    const FILE = encodeURIComponent(
      "hse-cs-sse/templates/coursework/versions/2026.1.3/version.yaml",
    );
    it.each([
      [
        `${BASE}/result/hse-cs-sse/coursework/2026.1.3?ux=2`,
        `${DRAFT}/result?ux=2`,
      ],
      [
        `${BASE}/result/hse-cs-sse/coursework/2026.1.3?ux=2&selected=documents%3Ats&i.kind=research&scenario=c1`,
        `${DRAFT}/result?ux=2&sel=documents%3Ats&i.kind=research&case=c1`,
      ],
      [
        `${BASE}/result/hse-cs-sse/coursework/2026.1.3?ux=2&view=atlas`,
        `${DRAFT}/check?ux=2&part=map`,
      ],
      [`${BASE}/result?ux=2`, `${DEFAULT}/result?ux=2`],
      [`${BASE}?ux=2&file=${FILE}`, `${DRAFT}/content?file=${FILE}&ux=2`],
      [`${BASE}?ux=2&view=files`, `${DEFAULT}/content?ux=2&part=files`],
      [
        `${BASE}?ux=2&view=files&newVersion=hse-cs-sse%2Fcoursework`,
        `${DEFAULT}/result?ux=2&copy=1`,
      ],
    ])("%s", async (from, to) => {
      open(from);
      await shell();
      expect(where()).toBe(to);
    });

    it("память последнего места: вход в корень возвращает версию, вкладку и условия", async () => {
      open(`${DRAFT}/check?ux=2&i.kind=research`);
      await shell();
      cleanup();
      open(BASE);
      await shell();
      expect(where()).toBe(`${DRAFT}/check?i.kind=research`);
    });
  });

  describe("?ux=2: особые состояния", () => {
    it("пространство клонируется: сообщение вместо оболочки", async () => {
      open(`${DRAFT}/result?ux=2`, {
        workspace: { state: "cloning", busy: true },
      });
      expect(await screen.findByTestId("ws-cloning")).toBeInTheDocument();
      expect(screen.queryByTestId("sp-shell")).toBeNull();
    });

    it("в пространстве нет версий: объяснение и возврат к списку", async () => {
      open(`${BASE}?ux=2`, { tree: { ...GALLERY_TREE, packs: [] } });
      expect(
        await screen.findByTestId("space-no-versions"),
      ).toBeInTheDocument();
    });
  });
});
