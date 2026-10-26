import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { act, cleanup, render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter, Route, Routes, useLocation } from "react-router";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { useUIStore } from "@shared/lib";
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

const mount = () =>
  render(
    <QueryClientProvider client={new QueryClient()}>
      <MemoryRouter initialEntries={["/"]}>
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
