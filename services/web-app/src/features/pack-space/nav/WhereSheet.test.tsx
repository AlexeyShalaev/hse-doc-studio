import { cleanup, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeAll, beforeEach, describe, expect, it } from "vitest";
import { installViewport } from "@shared/lib/viewport/testing";
import { loadPackSpaceNamespace } from "@shared/lib/i18n/packSpaceNamespace";
import { ContextBar } from "./ContextBar";
import { EDITED } from "./fixtures";
import { RELEASED_URL, renderNav } from "./navTestKit";

const T = "/pack-studio/w/gallery-ws/t";
const location = () => screen.getByTestId("location").textContent;

describe("шторка «Куда перейти» (телефон)", () => {
  let viewport: ReturnType<typeof installViewport> | undefined;
  beforeAll(async () => {
    await loadPackSpaceNamespace();
  });
  beforeEach(() => {
    window.localStorage.clear();
    viewport = installViewport(390);
  });
  afterEach(() => {
    cleanup();
    viewport?.restore();
  });

  it("одна кнопка: шаблон, версия и состояние словом", () => {
    renderNav(<ContextBar />, { url: RELEASED_URL });
    const button = screen.getByTestId("sp-where");
    expect(button).toHaveTextContent("Курсовой проект · 2026.1.2");
    expect(button).toHaveTextContent("выпущена");
  });

  it("шторка: «Мои правки» сверху, потом пак, шаблон и версия", async () => {
    const user = userEvent.setup();
    renderNav(<ContextBar />, { url: RELEASED_URL, changed: EDITED });
    await user.click(screen.getByTestId("sp-where"));
    const dialog = await screen.findByRole("dialog", { name: "Куда перейти" });
    expect(dialog).toHaveAttribute("data-form", "sheet");
    const mine = within(dialog).getByTestId("sp-where-mine");
    expect(mine).toHaveTextContent("Мои правки");
    expect(mine).toHaveTextContent(
      "Курсовой проект, версия 2026.1.3, 3 файла изменено",
    );
    // Текущие значения отмечены.
    expect(
      within(dialog).getByTestId("sp-where-pack-hse-cs-sse"),
    ).toHaveAttribute("aria-current", "true");
    expect(
      within(dialog).getByTestId("sp-where-version-2026.1.2"),
    ).toHaveAttribute("aria-current", "true");
    expect(
      within(dialog).getByTestId("sp-where-version-2026.1.3"),
    ).toHaveTextContent("черновик");
  });

  it("«Мои правки» ведёт прямо к черновику и закрывает шторку", async () => {
    const user = userEvent.setup();
    renderNav(<ContextBar />, { url: RELEASED_URL, changed: EDITED });
    await user.click(screen.getByTestId("sp-where"));
    await user.click(await screen.findByTestId("sp-where-mine"));
    expect(location()).toBe(`${T}/hse-cs-sse/coursework/2026.1.3/result`);
    expect(screen.queryByRole("dialog")).toBeNull();
  });

  it("без изменений карточки «Мои правки» нет", async () => {
    const user = userEvent.setup();
    renderNav(<ContextBar />, { url: RELEASED_URL });
    await user.click(screen.getByTestId("sp-where"));
    await screen.findByTestId("sp-where-body");
    expect(screen.queryByTestId("sp-where-mine")).toBeNull();
  });

  it("пак переключается сразу, шторка остаётся; версия закрывает её", async () => {
    const user = userEvent.setup();
    renderNav(<ContextBar />);
    await user.click(screen.getByTestId("sp-where"));
    await user.click(await screen.findByTestId("sp-where-pack-hse-cs-msc"));
    expect(location()).toBe(`${T}/hse-cs-msc/thesis/2026.1.1/result`);
    expect(screen.getByTestId("sp-where-body")).toBeInTheDocument();
    // Версии нового места видны в той же шторке.
    await user.click(screen.getByTestId("sp-where-version-2026.1.2"));
    expect(location()).toBe(`${T}/hse-cs-msc/thesis/2026.1.2/result`);
    expect(screen.queryByRole("dialog")).toBeNull();
  });

  it("Esc закрывает шторку", async () => {
    const user = userEvent.setup();
    renderNav(<ContextBar />);
    await user.click(screen.getByTestId("sp-where"));
    await screen.findByRole("dialog");
    await user.keyboard("{Escape}");
    expect(screen.queryByRole("dialog")).toBeNull();
  });
});
