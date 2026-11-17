import { readFileSync } from "node:fs";
import { join } from "node:path";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { cleanup, render, screen, waitFor } from "@testing-library/react";
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
import {
  PackGitSchema,
  PackProposeResponseSchema,
  packStudioApi,
  packStudioKeys,
  type PackGit,
  type PackTree,
} from "@entities/pack-studio";
import {
  installOutcomeReference,
  modesCalls,
  outcomeReference,
  scenarioReference,
  setModesBehavior,
} from "@entities/pack-studio/reference";
import { i18n } from "@shared/lib";
import { loadPackOutcomeNamespace } from "@shared/lib/i18n/packOutcomeNamespace";
import { loadPackStudioNamespace } from "@shared/lib/i18n/packStudioNamespace";
import { OutcomeBody } from "../OutcomeBody";

// «Предложить» на экране «Результат» (F10): тот же диалог, блок «до и после» на эталоне контракта.

const FIXTURES = join(
  import.meta.dirname,
  "../../../../../../contracts/pack-studio/fixtures",
);
const read = (dir: string, name: string): unknown =>
  JSON.parse(readFileSync(join(FIXTURES, dir, `${name}.json`), "utf8"));
const BASE_GIT = PackGitSchema.parse(read("PackGit", "detached_dirty"));
const PR = PackProposeResponseSchema.parse(
  read("PackProposeResponse", "github_pr"),
);
const VERSION = {
  pack: "hse-cs-sse",
  template: "coursework",
  version: "2026.1.6",
};
const WS = "ws-propose";

const git: PackGit = {
  ...BASE_GIT,
  workspace: { ...BASE_GIT.workspace, id: WS },
  changed: [
    {
      path: `${VERSION.pack}/templates/${VERSION.template}/versions/${VERSION.version}/version.yaml`,
      status: "modified",
    },
  ],
};

const tree: PackTree = {
  workspace_id: WS,
  base_sha: null,
  packs: [
    {
      id: VERSION.pack,
      path: VERSION.pack,
      name: { ru: "ФКН, СПИ" },
      templates: [
        {
          id: VERSION.template,
          path: `${VERSION.pack}/templates/${VERSION.template}`,
          name: { ru: "Курсовой проект" },
          default_version: VERSION.version,
          versions: [
            {
              version: VERSION.version,
              path: `${VERSION.pack}/templates/${VERSION.template}/versions/${VERSION.version}`,
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

const mount = (kind: "git" | "folder" = "git") => {
  vi.spyOn(packStudioApi, "git").mockResolvedValue(git);
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false, gcTime: Infinity } },
  });
  client.setQueryData(packStudioKeys.tree(WS), tree);
  render(
    <QueryClientProvider client={client}>
      <MemoryRouter
        initialEntries={[
          `/pack-studio/w/${WS}/result/${VERSION.pack}/${VERSION.template}/${VERSION.version}`,
        ]}
      >
        <OutcomeBody workspace={{ ...git.workspace, kind }} version={VERSION} />
      </MemoryRouter>
    </QueryClientProvider>,
  );
};

describe("«Предложить» на экране «Результат» (F10)", () => {
  beforeAll(async () => {
    installOutcomeReference();
    await Promise.all([loadPackOutcomeNamespace(), loadPackStudioNamespace()]);
    await i18n.changeLanguage("ru");
  });
  beforeEach(() => {
    outcomeReference.setSource("reference");
    scenarioReference.reset();
    setModesBehavior("normal");
    modesCalls.reset();
  });
  afterEach(() => {
    cleanup();
    vi.restoreAllMocks();
    setModesBehavior("normal");
  });

  it("кнопка есть в git-пространстве с правками; «до и после» не считается, пока диалог закрыт", async () => {
    mount();
    const button = await screen.findByTestId("outcome-propose");
    await waitFor(() => {
      expect(button).toBeEnabled();
    });
    expect(modesCalls.count("impact")).toBe(0);
  });

  it("клик открывает диалог: «изменится результат в 1 из 3», отметка обязательна, затем PR", async () => {
    const propose = vi.spyOn(packStudioApi, "propose").mockResolvedValue(PR);
    mount();
    await userEvent.click(await screen.findByTestId("outcome-propose"));
    expect(await screen.findByTestId("impact-headline")).toHaveTextContent(
      "Изменится результат в 1 из 3 сценариев",
    );
    expect(modesCalls.count("impact")).toBe(1);
    const submit = screen.getByTestId("git-propose-submit");
    await waitFor(() => {
      expect(submit).toHaveTextContent("Предложить всё равно");
    });
    expect(submit).toBeDisabled();
    await userEvent.click(await screen.findByTestId("git-propose-ack-input"));
    await userEvent.click(submit);
    await waitFor(() => {
      expect(propose).toHaveBeenCalled();
    });
  });

  it("повторное открытие без изменений берёт кэш, второго расчёта нет", async () => {
    vi.spyOn(packStudioApi, "propose").mockResolvedValue(PR);
    mount();
    await userEvent.click(await screen.findByTestId("outcome-propose"));
    await screen.findByTestId("impact-headline");
    await userEvent.click(screen.getByRole("button", { name: "Отмена" }));
    await waitFor(() => {
      expect(screen.queryByTestId("git-propose")).toBeNull();
    });
    await userEvent.click(screen.getByTestId("outcome-propose"));
    await screen.findByTestId("impact-headline");
    expect(modesCalls.count("impact")).toBe(1);
  });

  it("папка без git: кнопки нет", async () => {
    mount("folder");
    await screen.findByTestId("outcome-screen");
    expect(screen.queryByTestId("outcome-propose")).toBeNull();
  });
});
