import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { cleanup, render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter, Route, Routes, useLocation } from "react-router";
import { afterEach, beforeAll, describe, expect, it, vi } from "vitest";
import {
  packStudioKeys,
  type PackTree,
  type PackWorkspace,
} from "@entities/pack-studio";
import { i18n } from "@shared/lib";
import { loadPackStudioNamespace } from "@shared/lib/i18n/packStudioNamespace";
import { OutcomeEntry } from "./OutcomeRoute";
import { WorkspaceEntry } from "./WorkspaceEntry";

// Режим «Файлы» тяжёлый (редактор, дерево): здесь важно только, кто и когда его открывает.
vi.mock("./WorkspaceScreen", () => ({
  WorkspaceScreen: () => <div data-testid="files-mode" />,
}));

const WS = "ws-1";
const NOW = "2026-11-16T09:30:00Z";
const workspace = (state: PackWorkspace["state"]): PackWorkspace => ({
  id: WS,
  kind: "folder",
  label: "packs",
  state,
  busy: false,
  packs_path: "packs",
  url: null,
  credential_id: null,
  service_access: false,
  insecure_http: false,
  folder: "/work/packs",
  base_branch: null,
  base_sha: null,
  fetched_at: null,
  work_branch: null,
  pr_url: null,
  pr_number: null,
  ci_status: null,
  fork_url: null,
  pushed_sha: null,
  error: null,
  created_at: NOW,
  updated_at: NOW,
});

const tree = (versions: boolean): PackTree => ({
  workspace_id: WS,
  base_sha: null,
  packs: [
    {
      id: "hse-cs-sse",
      path: "hse-cs-sse",
      name: null,
      templates: [
        {
          id: "coursework",
          path: "hse-cs-sse/templates/coursework",
          name: null,
          default_version: "2026.1.5",
          versions: versions
            ? [
                {
                  version: "2026.1.5",
                  path: "hse-cs-sse/templates/coursework/versions/2026.1.5",
                  status: "stable",
                  released: true,
                  modified: false,
                },
                {
                  version: "2026.1.6",
                  path: "hse-cs-sse/templates/coursework/versions/2026.1.6",
                  status: "beta",
                  released: false,
                  modified: false,
                },
              ]
            : [],
        },
      ],
    },
  ],
  files: [],
  truncated: false,
});

const Probe = () => {
  const { pathname, search } = useLocation();
  return <output data-testid="location">{`${pathname}${search}`}</output>;
};

const open = (url: string, versions = true) => {
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false, staleTime: Infinity } },
  });
  client.setQueryData(packStudioKeys.workspace(WS), workspace("ready"));
  client.setQueryData(packStudioKeys.tree(WS), tree(versions));
  render(
    <QueryClientProvider client={client}>
      <MemoryRouter initialEntries={[url]}>
        <Routes>
          <Route
            path="/pack-studio/w/:workspaceId"
            element={<WorkspaceEntry />}
          />
          <Route
            path="/pack-studio/w/:workspaceId/result"
            element={<OutcomeEntry />}
          />
          <Route
            path="/pack-studio/w/:workspaceId/result/:pack/:template/:version"
            element={<div data-testid="outcome-page" />}
          />
        </Routes>
        <Probe />
      </MemoryRouter>
    </QueryClientProvider>,
  );
};

describe("вход в пространство Студии шаблонов", () => {
  beforeAll(async () => {
    await loadPackStudioNamespace();
    await i18n.changeLanguage("ru");
  });
  afterEach(cleanup);

  it("корень пространства открывает экран «Результат» версии по умолчанию", async () => {
    open(`/pack-studio/w/${WS}`);
    await waitFor(() => {
      expect(screen.getByTestId("outcome-page")).toBeInTheDocument();
    });
    expect(screen.getByTestId("location")).toHaveTextContent(
      `/pack-studio/w/${WS}/result/hse-cs-sse/coursework/2026.1.5`,
    );
  });

  it("вход без версии сохраняет состояние из адреса", async () => {
    open(`/pack-studio/w/${WS}/result?mode=student&i.kind=research`);
    await waitFor(() => {
      expect(screen.getByTestId("outcome-page")).toBeInTheDocument();
    });
    expect(screen.getByTestId("location")).toHaveTextContent(
      "/result/hse-cs-sse/coursework/2026.1.5?mode=student&i.kind=research",
    );
  });

  it("ссылка на файл по-прежнему открывает режим «Файлы»", () => {
    open(`/pack-studio/w/${WS}?file=hse-cs-sse/pack.yaml`);
    expect(screen.getByTestId("files-mode")).toBeInTheDocument();
    expect(screen.getByTestId("location")).toHaveTextContent("?file=");
  });

  it("?view=files открывает режим «Файлы» без файла", () => {
    open(`/pack-studio/w/${WS}?view=files`);
    expect(screen.getByTestId("files-mode")).toBeInTheDocument();
  });

  it("без версий в дереве: подсказка и переход в режим «Файлы»", async () => {
    open(`/pack-studio/w/${WS}`, false);
    const empty = await screen.findByTestId("outcome-no-versions");
    expect(empty).toHaveTextContent("нет версий шаблонов");
    expect(empty.querySelector("a")?.getAttribute("href")).toBe(
      `/pack-studio/w/${WS}?view=files`,
    );
  });
});
