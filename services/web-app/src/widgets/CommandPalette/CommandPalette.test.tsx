import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { act, cleanup, render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter, Route, Routes, useLocation } from "react-router";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { useUIStore, usePackStudioCommand } from "@shared/lib";
import { i18n } from "@shared/lib/i18n";

vi.mock("@entities/project", async () => ({
  ...(await vi.importActual<Record<string, unknown>>("@entities/project")),
  useProjects: () => ({ data: [] }),
}));

import { CommandPalette } from "./CommandPalette";

const Where = () => {
  const location = useLocation();
  return (
    <div data-testid="where">{`${location.pathname}${location.search}`}</div>
  );
};

const mount = (url = "/") =>
  render(
    <QueryClientProvider client={new QueryClient()}>
      <MemoryRouter initialEntries={[url]}>
        <CommandPalette />
        <Routes>
          <Route path="*" element={<Where />} />
        </Routes>
      </MemoryRouter>
    </QueryClientProvider>,
  );

describe("палитра команд: клонирование из git", () => {
  beforeEach(async () => {
    await i18n.changeLanguage("ru");
    act(() => {
      useUIStore.getState().setPaletteOpen(true);
    });
  });
  afterEach(() => {
    cleanup();
    act(() => {
      useUIStore.getState().setPaletteOpen(false);
    });
  });

  it("находит команду по названию и по части слова", async () => {
    const user = userEvent.setup();
    mount();
    expect(
      await screen.findByRole("button", { name: /Клонировать проект из git/ }),
    ).toBeInTheDocument();
    await user.type(screen.getByRole("textbox"), "клонир");
    expect(
      screen.getByRole("button", { name: /Клонировать проект из git/ }),
    ).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /Настройки/ })).toBeNull();
  });

  it("открывает мастер клонирования и закрывает палитру", async () => {
    const user = userEvent.setup();
    mount();
    await user.click(
      await screen.findByRole("button", { name: /Клонировать проект из git/ }),
    );
    expect(await screen.findByTestId("where")).toHaveTextContent(
      "/wizard?mode=clone",
    );
    expect(useUIStore.getState().paletteOpen).toBe(false);
  });
});

const Listener = ({
  command,
  onRun,
}: {
  command: "where" | "submit";
  onRun: () => void;
}) => {
  usePackStudioCommand(command, onRun);
  return null;
};

describe("палитра команд: Студия шаблонов", () => {
  const SPACE = "/pack-studio/w/ws1/t/hse-cs-sse/coursework/2026.1.3/result";
  beforeEach(async () => {
    await i18n.changeLanguage("ru");
    act(() => {
      useUIStore.getState().setPaletteOpen(true);
    });
  });
  afterEach(() => {
    cleanup();
    act(() => {
      useUIStore.getState().setPaletteOpen(false);
    });
  });

  it("предлагает «Перейти к…» и «Отправить на рассмотрение», не предлагает команды про проекты", async () => {
    mount(SPACE);
    expect(
      await screen.findByRole("button", {
        name: /Перейти к: пак, шаблон, версия/,
      }),
    ).toBeInTheDocument();
    expect(
      screen.getByRole("button", { name: /Отправить на рассмотрение/ }),
    ).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /Новый проект/ })).toBeNull();
    expect(
      screen.queryByRole("button", { name: /Клонировать проект/ }),
    ).toBeNull();
    expect(
      screen.getByRole("button", { name: /Настройки/ }),
    ).toBeInTheDocument();
  });

  it("команды доходят до экрана пространства и закрывают палитру", async () => {
    const where = vi.fn();
    const submit = vi.fn();
    const user = userEvent.setup();
    render(
      <QueryClientProvider client={new QueryClient()}>
        <MemoryRouter initialEntries={[SPACE]}>
          <CommandPalette />
          <Listener command="where" onRun={where} />
          <Listener command="submit" onRun={submit} />
        </MemoryRouter>
      </QueryClientProvider>,
    );
    await user.click(
      await screen.findByRole("button", { name: /Перейти к: пак/ }),
    );
    expect(where).toHaveBeenCalledTimes(1);
    expect(useUIStore.getState().paletteOpen).toBe(false);
    act(() => {
      useUIStore.getState().setPaletteOpen(true);
    });
    await user.click(
      await screen.findByRole("button", { name: /Отправить на рассмотрение/ }),
    );
    expect(submit).toHaveBeenCalledTimes(1);
    expect(where).toHaveBeenCalledTimes(1);
  });

  it("вне Студии шаблонов этих команд нет, а проектные на месте", async () => {
    mount("/");
    expect(
      await screen.findByRole("button", { name: /Новый проект/ }),
    ).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /Перейти к: пак/ })).toBeNull();
    expect(
      screen.queryByRole("button", { name: /Отправить на рассмотрение/ }),
    ).toBeNull();
  });
});
