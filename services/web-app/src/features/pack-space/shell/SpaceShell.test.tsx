import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { readFileSync } from "node:fs";
import { join } from "node:path";
import { afterEach, beforeAll, describe, expect, it, vi } from "vitest";
import { loadPackSpaceNamespace } from "@shared/lib/i18n/packSpaceNamespace";
import { SpaceShell, type SpaceShellProps } from "./SpaceShell";

const slots = (patch: Partial<SpaceShellProps> = {}): SpaceShellProps => ({
  header: <span>header</span>,
  actions: <button>actions</button>,
  contextBar: <span>context</span>,
  nav: <span>nav</span>,
  mainTop: <span>mainTop</span>,
  main: <span>main</span>,
  details: <span>details</span>,
  changes: <span>changes</span>,
  bottomTabs: <span>bottom</span>,
  ...patch,
});

describe("SpaceShell", () => {
  beforeAll(async () => {
    await loadPackSpaceNamespace();
  });
  afterEach(cleanup);

  it("десктоп и планшет: все слоты на месте, нижних вкладок нет", () => {
    render(<SpaceShell {...slots()} />);
    for (const text of [
      "header",
      "actions",
      "context",
      "nav",
      "mainTop",
      "main",
      "details",
    ]) {
      expect(screen.getByText(text)).toBeInTheDocument();
    }
    expect(screen.queryByTestId("sp-bottom")).toBeNull();
    expect(screen.queryByText("changes")).toBeNull();
    expect(screen.getByTestId("sp-shell")).not.toHaveAttribute("data-phone");
  });

  it("«Пропустить к содержимому» первая по Tab и переводит фокус в центр", () => {
    render(<SpaceShell {...slots()} />);
    const skip = screen.getByRole("link", { name: "Пропустить к содержимому" });
    const all = [...document.querySelectorAll<HTMLElement>("a, button")];
    expect(all[0]).toBe(skip);
    fireEvent.click(skip);
    expect(screen.getByTestId("sp-main")).toHaveFocus();
  });

  it("подробности выезжают по выбору: data-open следует за detailsOpen", () => {
    const { rerender } = render(<SpaceShell {...slots()} />);
    expect(screen.getByTestId("sp-side")).toHaveAttribute("data-open", "false");
    rerender(<SpaceShell {...slots({ detailsOpen: true })} />);
    expect(screen.getByTestId("sp-side")).toHaveAttribute("data-open", "true");
  });

  it("крестик и Esc закрывают выехавшую панель, Esc при закрытой ничего не делает", () => {
    const close = vi.fn();
    const { rerender } = render(
      <SpaceShell {...slots({ detailsOpen: true, onSideClose: close })} />,
    );
    fireEvent.click(screen.getByRole("button", { name: "Закрыть" }));
    expect(close).toHaveBeenCalledTimes(1);
    fireEvent.keyDown(screen.getByText("details"), { key: "Escape" });
    expect(close).toHaveBeenCalledTimes(2);
    fireEvent.keyDown(screen.getByText("details"), { key: "Enter" });
    expect(close).toHaveBeenCalledTimes(2);
    rerender(<SpaceShell {...slots({ onSideClose: close })} />);
    fireEvent.keyDown(screen.getByText("details"), { key: "Escape" });
    expect(close).toHaveBeenCalledTimes(2);
  });

  it("панель «Изменения» занимает место подробностей, без крестика каркаса", () => {
    render(
      <SpaceShell {...slots({ changesOpen: true, onSideClose: vi.fn() })} />,
    );
    expect(screen.getByText("changes")).toBeInTheDocument();
    expect(screen.queryByText("details")).toBeNull();
    expect(screen.queryByRole("button", { name: "Закрыть" })).toBeNull();
  });

  it("«Изменения» открыты, а слота панели нет: остаются подробности", () => {
    render(
      <SpaceShell {...slots({ changes: undefined, changesOpen: true })} />,
    );
    expect(screen.getByText("details")).toBeInTheDocument();
  });

  it("телефон: левой колонки нет, внизу вкладки, подробности шторкой", () => {
    render(<SpaceShell {...slots({ phone: true, detailsOpen: true })} />);
    expect(screen.queryByText("nav")).toBeNull();
    expect(screen.getByTestId("sp-bottom")).toHaveTextContent("bottom");
    expect(screen.getByTestId("sp-shell")).toHaveAttribute("data-phone");
    expect(screen.getByTestId("sp-side")).toHaveAttribute("data-open", "true");
  });

  it("телефон: «Изменения» это страница вместо экрана", () => {
    render(<SpaceShell {...slots({ phone: true, changesOpen: true })} />);
    expect(screen.getByTestId("sp-changes-page")).toHaveTextContent("changes");
    expect(screen.queryByText("main")).toBeNull();
    expect(screen.getByTestId("sp-bottom")).toBeInTheDocument();
  });

  it("слоты без содержимого не оставляют пустых рамок", () => {
    render(<SpaceShell header="h" main="m" />);
    for (const id of [
      "sp-context",
      "sp-nav",
      "sp-main-top",
      "sp-side",
      "sp-bottom",
    ]) {
      expect(screen.queryByTestId(id)).toBeNull();
    }
  });

  it("границы раскладки из документа записаны в стилях: 1100 px, колонки 232 и 360 px", () => {
    const css = readFileSync(
      join(import.meta.dirname, "space-shell.css"),
      "utf8",
    );
    expect(css).toContain("@container sp (min-width: 1100px)");
    expect(css).toContain("14.5rem"); // 232 px
    expect(css).toContain("22.5rem"); // 360 px
    expect(css).toContain("12.5rem"); // 200 px на планшете
  });
});
