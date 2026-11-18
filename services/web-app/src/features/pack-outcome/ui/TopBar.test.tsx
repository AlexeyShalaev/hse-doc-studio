import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import {
  cleanup,
  fireEvent,
  render,
  screen,
  within,
} from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter, useLocation } from "react-router";
import { afterEach, beforeAll, beforeEach, describe, expect, it } from "vitest";
import {
  packStudioKeys,
  type PackTree,
  type PackTreePack,
  type PackTreeTemplate,
  type PackVersionRef,
  type PackWorkspace,
} from "@entities/pack-studio";
import {
  installOutcomeReference,
  outcomeReference,
} from "@entities/pack-studio/reference";
import { i18n } from "@shared/lib";
import { loadPackOutcomeNamespace } from "@shared/lib/i18n/packOutcomeNamespace";
import { loadPackStudioNamespace } from "@shared/lib/i18n/packStudioNamespace";
import { installViewport } from "@shared/lib/viewport/testing";
import { OutcomeBody } from "../OutcomeBody";

// Верхняя панель: два связанных списка, «Пак» и «Шаблон» (шаблоны только выбранного пака).

const WS = "ws-bar";
const NOW = "2026-11-16T09:30:00Z";

const workspace = {
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
} as PackWorkspace;

const template = (
  pack: string,
  id: string,
  name: Record<string, string>,
  versions: string[],
  def: string,
): PackTreeTemplate => ({
  id,
  path: `${pack}/templates/${id}`,
  name,
  default_version: def,
  versions: versions.map((version) => ({
    version,
    path: `${pack}/templates/${id}/versions/${version}`,
    status: null,
    released: false,
    modified: false,
  })),
});

const pack = (
  id: string,
  name: Record<string, string>,
  templates: PackTreeTemplate[],
): PackTreePack => ({ id, path: id, name, templates });

const SE = pack("hse-cs-se", { ru: "ФКН, ПИ", en: "CS, SE" }, [
  template(
    "hse-cs-se",
    "vkr",
    { ru: "ВКР бакалавра", en: "Bachelor thesis" },
    ["2026.1.1", "2026.1.2"],
    "2026.1.1",
  ),
  template(
    "hse-cs-se",
    "kp",
    { ru: "Курсовой проект" },
    ["2026.1.1"],
    "2026.1.1",
  ),
]);
const SSE = pack("hse-cs-sse", { ru: "ФКН, МСПИ", en: "CS, SSE" }, [
  template("hse-cs-sse", "kp", { ru: "КП магистра" }, ["2026.2.0"], "2026.2.0"),
  template(
    "hse-cs-sse",
    "vkr",
    { ru: "ВКР магистра" },
    ["2026.2.1"],
    "2026.2.1",
  ),
]);

const treeOf = (packs: PackTreePack[]): PackTree => ({
  workspace_id: WS,
  base_sha: null,
  packs,
  files: [],
  truncated: false,
});

const Probe = () => {
  const { pathname, search } = useLocation();
  return <output data-testid="location">{`${pathname}${search}`}</output>;
};

const mount = (
  packs: PackTreePack[],
  path: string,
  version: PackVersionRef,
) => {
  const client = new QueryClient({
    defaultOptions: {
      queries: { retry: false, gcTime: Infinity, staleTime: Infinity },
    },
  });
  client.setQueryData(packStudioKeys.tree(WS), treeOf(packs));
  render(
    <QueryClientProvider client={client}>
      <MemoryRouter initialEntries={[`/pack-studio/w/${WS}/result/${path}`]}>
        <OutcomeBody workspace={workspace} version={version} />
        <Probe />
      </MemoryRouter>
    </QueryClientProvider>,
  );
};

const mountSe = (search = "") =>
  mount([SE, SSE], `hse-cs-se/vkr/2026.1.2${search}`, {
    pack: "hse-cs-se",
    template: "vkr",
    version: "2026.1.2",
  });

const location = () => screen.getByTestId("location").textContent;

const optionNames = async (name: string): Promise<string[]> => {
  await userEvent.click(screen.getByRole("combobox", { name }));
  const listbox = await screen.findByRole("listbox");
  return within(listbox)
    .getAllByRole("option")
    .map((o) => o.textContent ?? "");
};

const pick = async (select: string, option: string) => {
  await userEvent.click(screen.getByRole("combobox", { name: select }));
  await userEvent.click(await screen.findByRole("option", { name: option }));
};

describe("верхняя панель: пак и шаблон", () => {
  beforeAll(async () => {
    installOutcomeReference();
    await Promise.all([loadPackOutcomeNamespace(), loadPackStudioNamespace()]);
    const proto = Element.prototype as Partial<Element> & {
      hasPointerCapture?: (id: number) => boolean;
      releasePointerCapture?: (id: number) => void;
      scrollIntoView?: () => void;
    };
    proto.hasPointerCapture ??= () => false;
    proto.releasePointerCapture ??= () => undefined;
    proto.scrollIntoView ??= () => undefined;
  });
  beforeEach(async () => {
    window.localStorage.clear();
    outcomeReference.setSource("reference");
    await i18n.changeLanguage("ru");
  });
  afterEach(() => {
    cleanup();
    outcomeReference.setBehavior("normal");
    window.localStorage.clear();
  });

  it("два списка с подписями: пак с id и названием, шаблон из этого пака", async () => {
    mountSe();
    await screen.findByTestId("outcome-count-documents");
    const bar = screen.getByTestId("outcome-crumbs");
    const packBox = within(bar).getByRole("combobox", { name: "Пак" });
    const templateBox = within(bar).getByRole("combobox", { name: "Шаблон" });
    expect(packBox).toHaveTextContent("hse-cs-se · ФКН, ПИ");
    expect(templateBox).toHaveTextContent("ВКР бакалавра");
    expect(within(bar).getByRole("combobox", { name: "Версия" })).toBeVisible();
    expect(await optionNames("Пак")).toEqual([
      "hse-cs-se · ФКН, ПИ",
      "hse-cs-sse · ФКН, МСПИ",
    ]);
  });

  it("в списке шаблонов только шаблоны выбранного пака, в порядке манифеста", async () => {
    mountSe();
    await screen.findByTestId("outcome-count-documents");
    expect(await optionNames("Шаблон")).toEqual([
      "ВКР бакалавра",
      "Курсовой проект",
    ]);
  });

  it("смена пака выбирает тот же шаблон в новом паке и его версию по умолчанию, сценарий сбрасывается", async () => {
    mountSe("?scenario=solo&state=head&mode=student");
    await screen.findByTestId("outcome-student");
    await pick("Пак", "hse-cs-sse · ФКН, МСПИ");
    expect(location()).toBe(
      `/pack-studio/w/${WS}/result/hse-cs-sse/vkr/2026.2.1?state=head&mode=student`,
    );
  });

  it("смена пака без такого же шаблона выбирает первый шаблон пака", async () => {
    mount(
      [
        SE,
        pack("hse-cs-sse", { ru: "МСПИ" }, [
          template("hse-cs-sse", "kp", { ru: "КП магистра" }, ["1", "2"], "1"),
        ]),
      ],
      "hse-cs-se/vkr/2026.1.2",
      { pack: "hse-cs-se", template: "vkr", version: "2026.1.2" },
    );
    await screen.findByTestId("outcome-count-documents");
    await pick("Пак", "hse-cs-sse · МСПИ");
    expect(location()).toBe(`/pack-studio/w/${WS}/result/hse-cs-sse/kp/1`);
  });

  it("смена шаблона в том же паке сохраняет режим и состояние, версия по умолчанию", async () => {
    mountSe("?mode=student&state=head");
    await screen.findByTestId("outcome-student");
    await pick("Шаблон", "Курсовой проект");
    expect(location()).toBe(
      `/pack-studio/w/${WS}/result/hse-cs-se/kp/2026.1.1?state=head&mode=student`,
    );
  });

  it("один пак и один шаблон: оба списка на месте", async () => {
    const only = pack("solo", { ru: "Один" }, [
      template("solo", "vkr", { ru: "Единственный" }, ["1.0"], "1.0"),
    ]);
    mount([only], "solo/vkr/1.0", {
      pack: "solo",
      template: "vkr",
      version: "1.0",
    });
    await screen.findByTestId("outcome-crumbs");
    const bar = screen.getByTestId("outcome-crumbs");
    expect(
      within(bar).getByRole("combobox", { name: "Пак" }),
    ).toHaveTextContent("solo · Один");
    expect(
      within(bar).getByRole("combobox", { name: "Шаблон" }),
    ).toHaveTextContent("Единственный");
    expect(await optionNames("Шаблон")).toEqual(["Единственный"]);
  });

  it("клавиатура: пак выбирается стрелками и Enter", async () => {
    mountSe();
    await screen.findByTestId("outcome-count-documents");
    const box = screen.getByRole("combobox", { name: "Пак" });
    box.focus();
    await userEvent.keyboard("{ArrowDown}");
    await screen.findByRole("listbox");
    await userEvent.keyboard("{ArrowDown}{Enter}");
    expect(location()).toContain("/result/hse-cs-sse/vkr/2026.2.1");
  });

  it("английский: подписи и названия из манифестов на en", async () => {
    await i18n.changeLanguage("en");
    mountSe();
    await screen.findByTestId("outcome-count-documents");
    const bar = screen.getByTestId("outcome-crumbs");
    expect(
      within(bar).getByRole("combobox", { name: "Pack" }),
    ).toHaveTextContent("hse-cs-se · CS, SE");
    expect(
      within(bar).getByRole("combobox", { name: "Template" }),
    ).toHaveTextContent("Bachelor thesis");
  });

  it("старая ссылка /result/<пак>/<шаблон>/<версия> открывается с теми же значениями", async () => {
    mount([SE, SSE], "hse-cs-sse/kp/2026.2.0", {
      pack: "hse-cs-sse",
      template: "kp",
      version: "2026.2.0",
    });
    await screen.findByTestId("outcome-crumbs");
    expect(screen.getByRole("combobox", { name: "Пак" })).toHaveTextContent(
      "hse-cs-sse",
    );
    expect(screen.getByRole("combobox", { name: "Шаблон" })).toHaveTextContent(
      "КП магистра",
    );
  });

  it("телефон: оба списка в листе «Параметры», в панели только название", async () => {
    const viewport = installViewport(360);
    try {
      mountSe();
      await screen.findByTestId("outcome-count-documents");
      const bar = screen.getByTestId("outcome-phone-bar");
      expect(within(bar).queryByRole("combobox", { name: "Пак" })).toBeNull();
      fireEvent.click(screen.getByTestId("outcome-options-open"));
      const options = await screen.findByTestId("outcome-options");
      expect(
        within(options).getByRole("combobox", { name: "Пак" }),
      ).toBeInTheDocument();
      expect(
        within(options).getByRole("combobox", { name: "Шаблон" }),
      ).toBeInTheDocument();
    } finally {
      viewport.restore();
    }
  });
});
