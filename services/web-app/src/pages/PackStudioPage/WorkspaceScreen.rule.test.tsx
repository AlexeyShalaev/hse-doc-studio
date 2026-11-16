import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { cleanup, render, screen } from "@testing-library/react";
import { MemoryRouter, Route, Routes } from "react-router";
import { afterEach, beforeAll, describe, expect, it, vi } from "vitest";
import {
  packOutcomePath,
  packRulePath,
  packStudioKeys,
  type PackTree,
  type PackWorkspace,
} from "@entities/pack-studio";
import { LOCAL_BOOTSTRAP, sessionKeys } from "@entities/session";
import { i18n } from "@shared/lib";
import { loadPackStudioNamespace } from "@shared/lib/i18n/packStudioNamespace";
import { WorkspaceScreen } from "./WorkspaceScreen";

// Переход к правилу из экрана «Результат»: режим «Файлы» понимает `at`, `pane`, `from`.
// Тяжёлые части (редактор, дерево, git, форма) подменены заглушками, которые показывают, что им
// передали: так видно, что параметры адреса дошли до редактора и формы и что возврат безопасен.

vi.mock("@features/pack-file-editor", () => ({
  PackFileEditor: (props: {
    path: string;
    pointer?: string | null;
    initialView?: string;
    form?: React.ReactNode;
  }) => (
    <div
      data-testid="editor"
      data-path={props.path}
      data-pointer={props.pointer ?? ""}
      data-view={props.initialView ?? ""}
    >
      {props.form}
    </div>
  ),
}));
vi.mock("@features/pack-forms", () => ({
  PackFormPane: (props: { at?: string | null }) => (
    <div data-testid="form" data-at={props.at ?? ""} />
  ),
}));
vi.mock("@features/pack-git", () => ({ PackGitBar: () => null }));
vi.mock("@features/pack-places", () => ({ PackPlacesEditor: () => null }));
vi.mock("@features/pack-preview", () => ({ PackPreviewPane: () => null }));
vi.mock("@features/pack-tree", () => ({
  PackTreePanel: () => <div data-testid="tree" />,
  versionStatusVariant: () => "default",
}));
vi.mock("@features/pack-version", () => ({
  VersionBar: () => null,
  NewVersionDialog: () => null,
}));
vi.mock("@features/pack-scaffold", () => ({ NewPackDialog: () => null }));

const WS = "ws-rule";
const NOW = "2026-11-16T09:30:00Z";
const VERSION = "hse-cs-sse/templates/coursework/versions/2026.1.6";
const FILE = `${VERSION}/version.yaml`;
const REF = { pack: "hse-cs-sse", template: "coursework", version: "2026.1.6" };

const workspace: PackWorkspace = {
  id: WS,
  kind: "folder",
  label: "packs",
  state: "ready",
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
};

const tree: PackTree = {
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
          default_version: "2026.1.6",
          versions: [
            {
              version: "2026.1.6",
              path: VERSION,
              status: "beta",
              released: false,
              modified: false,
            },
          ],
        },
      ],
    },
  ],
  files: [],
  truncated: false,
};

const open = (url: string) => {
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false, staleTime: Infinity } },
  });
  client.setQueryData(sessionKeys.bootstrap(), {
    ...LOCAL_BOOTSTRAP,
    capabilities: {
      ...LOCAL_BOOTSTRAP.capabilities,
      pack_studio: true,
      pack_outcome: true,
    },
  });
  client.setQueryData(packStudioKeys.workspace(WS), workspace);
  client.setQueryData(packStudioKeys.tree(WS), tree);
  render(
    <QueryClientProvider client={client}>
      <MemoryRouter initialEntries={[url]}>
        <Routes>
          <Route
            path="/pack-studio/w/:workspaceId"
            element={<WorkspaceScreen />}
          />
        </Routes>
      </MemoryRouter>
    </QueryClientProvider>,
  );
};

describe("режим «Файлы» при переходе к правилу", () => {
  beforeAll(async () => {
    await loadPackStudioNamespace();
    await i18n.changeLanguage("ru");
  });
  afterEach(cleanup);

  const from = packOutcomePath(
    WS,
    REF,
    "selected=documents%3Areport&i.kind=research",
  );
  const rule = (pane: "form" | "source") =>
    packRulePath(WS, FILE, {
      pointer: "/pack_submission/profiles/0/signing_slots/0/when",
      pane,
      from,
    });

  it("указатель и вкладка доходят до редактора, указатель до формы", async () => {
    open(rule("form"));
    const editor = await screen.findByTestId("editor");
    expect(editor).toHaveAttribute("data-path", FILE);
    expect(editor).toHaveAttribute(
      "data-pointer",
      "/pack_submission/profiles/0/signing_slots/0/when",
    );
    expect(editor).toHaveAttribute("data-view", "form");
    expect(await screen.findByTestId("form")).toHaveAttribute(
      "data-at",
      "/pack_submission/profiles/0/signing_slots/0/when",
    );
  });

  it("вкладка «Исходник» передаётся редактору", async () => {
    open(rule("source"));
    expect(await screen.findByTestId("editor")).toHaveAttribute(
      "data-view",
      "source",
    );
  });

  it("«Назад к результату» ведёт на тот же результат с вводными и выбранным элементом", async () => {
    open(rule("form"));
    const back = await screen.findByTestId("ws-back-to-result");
    expect(back).toHaveTextContent("Назад к результату");
    expect(back).toHaveAttribute("href", from);
  });

  it("чужой адрес возврата отбрасывается, кнопки нет", async () => {
    open(
      `/pack-studio/w/${WS}?file=${encodeURIComponent(FILE)}&from=${encodeURIComponent("https://evil.example/x")}`,
    );
    await screen.findByTestId("editor");
    expect(screen.queryByTestId("ws-back-to-result")).not.toBeInTheDocument();
  });

  it("обычная ссылка на файл работает как раньше: ни указателя, ни вкладки, ни возврата", async () => {
    open(`/pack-studio/w/${WS}?file=${encodeURIComponent(FILE)}`);
    const editor = await screen.findByTestId("editor");
    expect(editor).toHaveAttribute("data-pointer", "");
    expect(editor).toHaveAttribute("data-view", "");
    expect(screen.queryByTestId("ws-back-to-result")).not.toBeInTheDocument();
  });
});
