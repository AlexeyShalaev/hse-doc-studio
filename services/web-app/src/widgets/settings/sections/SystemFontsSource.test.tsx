import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import type { SystemFontsListResponse } from "@entities/fonts";
import { i18n } from "@shared/lib/i18n";

// Ответ /fonts/system подменяется: компоненту важен только разбор причины.
const state: { data: SystemFontsListResponse | undefined } = {
  data: undefined,
};

vi.mock("@entities/fonts", async () => ({
  ...(await vi.importActual<Record<string, unknown>>("@entities/fonts")),
  useSystemFonts: () => ({ data: state.data, isLoading: false }),
  useImportSystemFonts: () => ({ mutate: vi.fn(), isPending: false }),
}));

import { SystemFontsSource } from "./SystemFontsSource";

describe("SystemFontsSource: шрифтов машины не видно", () => {
  beforeEach(async () => {
    await i18n.changeLanguage("ru");
  });
  afterEach(cleanup);

  it("Docker Desktop не отдал каталог: подсказка про macOS и как обойти", () => {
    state.data = { available: false, fonts: [], reason: "not_shared" };
    render(<SystemFontsSource />);

    const hint = screen.getByTestId("system-fonts-unavailable-hint");
    expect(hint).toHaveTextContent("/System/Library/Fonts/Supplemental");
    expect(hint).toHaveTextContent("Запустите установщик ещё раз");
  });

  it("шрифтов просто нет: прежняя общая подсказка", () => {
    state.data = { available: false, fonts: [], reason: "not_found" };
    render(<SystemFontsSource />);

    expect(
      screen.getByTestId("system-fonts-unavailable-hint"),
    ).not.toHaveTextContent("/System/Library/Fonts");
  });
});
