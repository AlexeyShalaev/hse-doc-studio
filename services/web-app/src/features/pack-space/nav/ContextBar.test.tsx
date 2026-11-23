import { cleanup, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeAll, beforeEach, describe, expect, it } from "vitest";
import { loadPackSpaceNamespace } from "@shared/lib/i18n/packSpaceNamespace";
import { readLastVersion } from "./lastVisited";
import { BASE, EDITED, TREE } from "./fixtures";
import { ContextBar } from "./ContextBar";
import { DRAFT_URL, RELEASED_URL, renderNav } from "./navTestKit";

const T = "/pack-studio/w/gallery-ws/t";
const location = () => screen.getByTestId("location").textContent;

describe("ContextBar: где я и куда перейти", () => {
  beforeAll(async () => {
    await loadPackSpaceNamespace();
  });
  beforeEach(() => {
    window.localStorage.clear();
  });
  afterEach(cleanup);

  it("пак, шаблон и версия словами, у версии состояние словом", () => {
    renderNav(<ContextBar />);
    expect(screen.getByTestId("sp-crumb-pack")).toHaveTextContent(
      "Программная инженерия",
    );
    expect(screen.getByTestId("sp-crumb-template")).toHaveTextContent(
      "Курсовой проект",
    );
    const version = screen.getByTestId("sp-crumb-version");
    expect(version).toHaveTextContent("Версия 2026.1.3");
    expect(within(version).getByTestId("sp-state-draft")).toHaveTextContent(
      "черновик",
    );
  });

  it("выпущенная версия: слово «выпущена» (и замок), а не «черновик»", () => {
    renderNav(<ContextBar />, { url: RELEASED_URL });
    const version = screen.getByTestId("sp-crumb-version");
    expect(version).toHaveTextContent("Версия 2026.1.2");
    expect(within(version).getByTestId("sp-state-released")).toHaveTextContent(
      "выпущена",
    );
    expect(within(version).queryByTestId("sp-state-draft")).toBeNull();
  });

  it("вкладки ведут на тот же пак, шаблон и версию", async () => {
    const user = userEvent.setup();
    renderNav(<ContextBar />);
    await user.click(screen.getByTestId("sp-tab-check"));
    expect(location()).toBe(`${T}/hse-cs-sse/coursework/2026.1.3/check`);
  });

  it("список версий: состояние у каждой и пометки, выбор меняет адрес", async () => {
    const user = userEvent.setup();
    renderNav(<ContextBar />, { changed: EDITED });
    await user.click(screen.getByTestId("sp-crumb-version"));
    const draft = await screen.findByTestId("sp-crumb-version-item-2026.1.3");
    const released = screen.getByTestId("sp-crumb-version-item-2026.1.2");
    expect(draft).toHaveTextContent("3 файла изменено");
    expect(draft).toHaveTextContent("черновик");
    expect(released).toHaveTextContent("по умолчанию");
    expect(released).toHaveTextContent("выпущена");
    // Новые версии сверху.
    const rows = screen.getAllByRole("menuitemradio");
    expect(rows.map((row) => row.getAttribute("data-testid"))).toEqual([
      "sp-crumb-version-item-2026.1.3",
      "sp-crumb-version-item-2026.1.2",
    ]);
    expect(draft).toHaveAttribute("aria-checked", "true");
    await user.click(released);
    expect(location()).toBe(`${T}/hse-cs-sse/coursework/2026.1.2/result`);
  });

  it("«Мои правки» в списке версий ведёт к черновику, когда открыта другая версия", async () => {
    const user = userEvent.setup();
    renderNav(<ContextBar />, { url: RELEASED_URL, changed: EDITED });
    await user.click(screen.getByTestId("sp-crumb-version"));
    const mine = await screen.findByRole("menuitem", {
      name: /Мои правки: Курсовой проект, 2026\.1\.3/,
    });
    await user.click(mine);
    expect(location()).toBe(`${T}/hse-cs-sse/coursework/2026.1.3/result`);
  });

  it("«Мои правки» не показывается, когда изменений нет или открыт сам черновик", async () => {
    const user = userEvent.setup();
    renderNav(<ContextBar />, { url: RELEASED_URL });
    await user.click(screen.getByTestId("sp-crumb-version"));
    await screen.findByTestId("sp-crumb-version-item-2026.1.3");
    expect(screen.queryByRole("menuitem")).toBeNull();
    await user.keyboard("{Escape}");
    cleanup();
    renderNav(<ContextBar />, { changed: EDITED });
    await user.click(screen.getByTestId("sp-crumb-version"));
    await screen.findByTestId("sp-crumb-version-item-2026.1.3");
    expect(screen.queryByRole("menuitem")).toBeNull();
  });

  it("смена пака не уводит с версии, где есть изменения", async () => {
    const user = userEvent.setup();
    // Правки в магистерском паке: его версия по умолчанию 2026.1.1, а правки в черновике 2026.1.2.
    const changed = ["hse-cs-msc/templates/thesis/versions/2026.1.2/a.tex"];
    renderNav(<ContextBar />, { changed });
    await user.click(screen.getByTestId("sp-crumb-pack"));
    await user.click(
      await screen.findByTestId("sp-crumb-pack-item-hse-cs-msc"),
    );
    expect(location()).toBe(`${T}/hse-cs-msc/thesis/2026.1.2/result`);
  });

  it("смена пака и возврат: открывается версия, где были, а не по умолчанию", async () => {
    const user = userEvent.setup();
    renderNav(<ContextBar />);
    // Были в черновике 2026.1.3 (запомнилось само), ушли в другой пак.
    expect(readLastVersion("gallery-ws", "hse-cs-sse", "coursework")).toBe(
      "2026.1.3",
    );
    await user.click(screen.getByTestId("sp-crumb-pack"));
    await user.click(
      await screen.findByTestId("sp-crumb-pack-item-hse-cs-msc"),
    );
    expect(location()).toBe(`${T}/hse-cs-msc/thesis/2026.1.1/result`);
    await user.click(screen.getByTestId("sp-crumb-pack"));
    await user.click(
      await screen.findByTestId("sp-crumb-pack-item-hse-cs-sse"),
    );
    expect(location()).toBe(`${T}/hse-cs-sse/coursework/2026.1.3/result`);
  });

  it("смена шаблона сохраняет условия студента и вкладку", async () => {
    const user = userEvent.setup();
    renderNav(<ContextBar />, {
      url: `${T}/hse-cs-sse/coursework/2026.1.3/content?i.kind=research&doc=ts`,
    });
    await user.click(screen.getByTestId("sp-crumb-version"));
    await user.click(
      await screen.findByTestId("sp-crumb-version-item-2026.1.2"),
    );
    // Условия переживают переход, параметры вкладки (doc) сбрасываются.
    expect(location()).toBe(
      `${T}/hse-cs-sse/coursework/2026.1.2/content?i.kind=research`,
    );
  });

  it("клавиатура: Enter открывает список, стрелки и Enter выбирают, Esc закрывает", async () => {
    const user = userEvent.setup();
    renderNav(<ContextBar />, { changed: EDITED });
    screen.getByTestId("sp-crumb-version").focus();
    await user.keyboard("{Enter}");
    expect(await screen.findByRole("menu")).toBeInTheDocument();
    await user.keyboard("{Escape}");
    expect(screen.queryByRole("menu")).toBeNull();
    expect(screen.getByTestId("sp-crumb-version")).toHaveFocus();
    await user.keyboard("{Enter}");
    await screen.findByRole("menu");
    await user.keyboard("{ArrowDown}{ArrowDown}{Enter}");
    expect(location()).toBe(`${T}/hse-cs-sse/coursework/2026.1.2/result`);
  });

  it("пак без шаблонов виден, но выбрать его нельзя: сказано почему", async () => {
    const user = userEvent.setup();
    renderNav(<ContextBar />, {
      tree: {
        ...TREE,
        packs: [
          ...TREE.packs,
          { id: "empty", path: "empty", name: null, templates: [] },
        ],
      },
    });
    await user.click(screen.getByTestId("sp-crumb-pack"));
    const row = await screen.findByTestId("sp-crumb-pack-item-empty");
    expect(row).toHaveTextContent("нет шаблонов");
    expect(row).toHaveAttribute("aria-disabled", "true");
  });

  it("кнопки пака и шаблона названы для скринридера", () => {
    renderNav(<ContextBar />);
    expect(
      screen.getByRole("button", { name: "Пак: Программная инженерия" }),
    ).toBeInTheDocument();
    expect(
      screen.getByRole("button", { name: "Шаблон: Курсовой проект" }),
    ).toBeInTheDocument();
  });

  it("в меню пака и шаблона есть «Создать пак» и «Создать шаблон»", async () => {
    const user = userEvent.setup();
    renderNav(<ContextBar />);
    await user.click(screen.getByTestId("sp-crumb-pack"));
    expect(
      await screen.findByRole("menuitem", { name: "Создать пак" }),
    ).toBeInTheDocument();
    await user.keyboard("{Escape}");
    await user.click(screen.getByTestId("sp-crumb-template"));
    expect(
      await screen.findByRole("menuitem", { name: "Создать шаблон" }),
    ).toBeInTheDocument();
  });

  it("BASE версии лежит в дереве: пути изменений совпадают с каталогами", () => {
    expect(EDITED.every((path) => path.startsWith(`${BASE}/2026.1.3/`))).toBe(
      true,
    );
    expect(DRAFT_URL).toContain("2026.1.3");
  });
});
