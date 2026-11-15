import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter, Route, Routes, useLocation } from "react-router";
import { afterEach, beforeAll, describe, expect, it, vi } from "vitest";
import { packStudioApi, type PackStudioSection } from "@entities/pack-studio";
import { i18n } from "@shared/lib";
import { PackStudioSettingsSection } from "./PackStudioSettingsSection";

const section = (
  patch: Partial<PackStudioSection> = {},
): PackStudioSection => ({
  enabled: false,
  locked: false,
  allowed: false,
  has_right: true,
  standalone: false,
  ...patch,
});

const Where = () => <span data-testid="where">{useLocation().pathname}</span>;

const mount = () =>
  render(
    <QueryClientProvider client={new QueryClient()}>
      <MemoryRouter initialEntries={["/settings/pack-studio"]}>
        <Where />
        <Routes>
          <Route
            path="/settings/:section"
            element={<PackStudioSettingsSection />}
          />
          <Route path="*" element={null} />
        </Routes>
      </MemoryRouter>
    </QueryClientProvider>,
  );

describe("Настройки: Студия шаблонов", () => {
  beforeAll(async () => {
    await i18n.changeLanguage("ru");
  });
  afterEach(() => {
    vi.restoreAllMocks();
  });

  it("переключатель включает раздел, после этого есть переход в Студию шаблонов", async () => {
    vi.spyOn(packStudioApi, "section").mockResolvedValue(section());
    const set = vi
      .spyOn(packStudioApi, "setSection")
      .mockResolvedValue(section({ enabled: true, allowed: true }));
    mount();
    const toggle = await screen.findByTestId("pack-studio-toggle");
    expect(screen.queryByTestId("pack-studio-open")).not.toBeInTheDocument();
    await userEvent.click(toggle);
    await waitFor(() => {
      expect(set).toHaveBeenCalledWith(true);
    });
    await userEvent.click(await screen.findByTestId("pack-studio-open"));
    expect(screen.getByTestId("where")).toHaveTextContent("/pack-studio");
  });

  it("задано при запуске: переключатель только для чтения", async () => {
    vi.spyOn(packStudioApi, "section").mockResolvedValue(
      section({ enabled: true, locked: true, allowed: true, standalone: true }),
    );
    mount();
    expect(await screen.findByTestId("pack-studio-toggle")).toBeDisabled();
    expect(
      screen.getByText(/Включение задано при запуске Студии/),
    ).toBeInTheDocument();
  });
});
