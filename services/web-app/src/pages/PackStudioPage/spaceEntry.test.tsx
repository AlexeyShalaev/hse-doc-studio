import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { cleanup, render, screen } from "@testing-library/react";
import { MemoryRouter, Route, Routes, useLocation } from "react-router";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import {
  packStudioKeys,
  resetPackStudioUx,
  type PackTree,
  type PackWorkspace,
} from "@entities/pack-studio";
import { loadPackSpaceNamespace } from "@shared/lib/i18n/packSpaceNamespace";
import { GALLERY_WORKSPACE } from "@features/pack-space/galleryKit";
import { BASE, TREE, gitStatus } from "@features/pack-space/nav/fixtures";
import { PackStudioApp } from "./PackStudioApp";

// Вход в пространство (S2): куда открыть, когда у человека есть изменения, и пространства без версий.
vi.mock("@widgets/AppTitlebar", () => ({ AppTitlebar: () => null }));
vi.mock("@widgets/AppStatusBar", () => ({ AppStatusBar: () => null }));
vi.mock("./WorkspacesScreen", () => ({ WorkspacesScreen: () => null }));
vi.mock("./WorkspaceEntry", () => ({ WorkspaceEntry: () => null }));
vi.mock("./OutcomeRoute", () => ({
  OutcomeEntry: () => null,
  OutcomeRoute: () => null,
}));

const WS = GALLERY_WORKSPACE.id;
const ENTRY = `/pack-studio/w/${WS}?ux=2`;
const T = `/pack-studio/w/${WS}/t`;

const Probe = () => {
  const { pathname, search } = useLocation();
  return <output data-testid="location">{`${pathname}${search}`}</output>;
};

const open = (
  url: string,
  {
    changed,
    tree = TREE,
    workspace = {},
  }: {
    changed?: string[];
    tree?: PackTree;
    workspace?: Partial<PackWorkspace>;
  } = {},
) => {
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false, staleTime: Infinity } },
  });
  client.setQueryData(packStudioKeys.workspace(WS), {
    ...GALLERY_WORKSPACE,
    ...workspace,
  });
  client.setQueryData(packStudioKeys.tree(WS), tree);
  if (changed) {
    client.setQueryData(packStudioKeys.git(WS), gitStatus(changed));
  }
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
// Чанк нового вида грузится лениво: под нагрузкой первый кадр бывает медленным.
const shell = () => screen.findByTestId("sp-shell", {}, { timeout: 8000 });

describe("вход в пространство нового вида: версия с моими изменениями", () => {
  beforeEach(async () => {
    await loadPackSpaceNamespace();
    resetPackStudioUx();
    window.localStorage.clear();
  });
  afterEach(() => {
    cleanup();
    resetPackStudioUx();
  });

  it("есть изменения в черновике: вход открывает его, а не версию по умолчанию", async () => {
    open(ENTRY, { changed: [`${BASE}/2026.1.3/version.yaml`] });
    await shell();
    expect(where()).toBe(`${T}/hse-cs-sse/coursework/2026.1.3/result?ux=2`);
  });

  it("изменений нет: версия по умолчанию", async () => {
    open(ENTRY, { changed: [] });
    await shell();
    expect(where()).toBe(`${T}/hse-cs-sse/coursework/2026.1.2/result?ux=2`);
  });

  it("изменения в другом шаблоне: открывается он", async () => {
    open(ENTRY, {
      changed: ["hse-cs-msc/templates/thesis/versions/2026.1.2/a.tex"],
    });
    await shell();
    expect(where()).toBe(`${T}/hse-cs-msc/thesis/2026.1.2/result?ux=2`);
  });

  it("в папке на диске git не спрашивается, вход не ждёт", async () => {
    open(ENTRY, { workspace: { kind: "folder" } });
    await shell();
    expect(where()).toBe(`${T}/hse-cs-sse/coursework/2026.1.2/result?ux=2`);
  });

  it("нет паков: причина и «Создать пак»", async () => {
    open(ENTRY, { changed: [], tree: { ...TREE, packs: [] } });
    const empty = await screen.findByTestId(
      "space-no-versions",
      {},
      { timeout: 8000 },
    );
    expect(empty).toHaveTextContent("В пространстве пока нет шаблонов");
    expect(screen.getByTestId("space-no-versions-create")).toHaveTextContent(
      "Создать пак",
    );
    // Шапка пространства есть и здесь: выход в список и меню не зависят от иконки приложения.
    expect(screen.getByTestId("sp-back")).toBeInTheDocument();
    expect(screen.getByTestId("sp-ws-menu")).toBeInTheDocument();
  });

  it("в паке нет шаблонов: «Создать шаблон»", async () => {
    const first = TREE.packs[0];
    open(ENTRY, {
      changed: [],
      tree: { ...TREE, packs: first ? [{ ...first, templates: [] }] : [] },
    });
    const empty = await screen.findByTestId(
      "space-no-versions",
      {},
      { timeout: 8000 },
    );
    expect(empty).toHaveTextContent("В паке «hse-cs-sse» нет шаблонов");
    expect(screen.getByTestId("space-no-versions-create")).toHaveTextContent(
      "Создать шаблон",
    );
  });

  it("у шаблона нет версий: объяснение и возврат к списку", async () => {
    const first = TREE.packs[0];
    const template = first?.templates[0];
    open(ENTRY, {
      changed: [],
      tree: {
        ...TREE,
        packs:
          first && template
            ? [{ ...first, templates: [{ ...template, versions: [] }] }]
            : [],
      },
    });
    const empty = await screen.findByTestId(
      "space-no-versions",
      {},
      { timeout: 8000 },
    );
    expect(empty).toHaveTextContent("У шаблона «coursework» нет версий");
    expect(screen.queryByTestId("space-no-versions-create")).toBeNull();
  });
});
