import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { cleanup, render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { useThemeStore } from "@shared/lib";
import { i18n } from "@shared/lib/i18n";
import { AppearanceSection } from "./AppearanceSection";

const mount = () =>
  render(
    <QueryClientProvider client={new QueryClient()}>
      <AppearanceSection />
    </QueryClientProvider>,
  );

describe("AppearanceSection: text size", () => {
  beforeEach(async () => {
    await i18n.changeLanguage("ru");
    useThemeStore.setState({ textScale: 100, textScaleChosen: false });
  });
  afterEach(() => {
    cleanup();
    vi.restoreAllMocks();
  });

  it("offers every step, the current one checked, and a live preview", () => {
    mount();
    const steps = screen.getAllByRole("radio");
    expect(steps.map((s) => s.textContent)).toEqual([
      "90%",
      "100%",
      "112%",
      "125%",
      "140%",
    ]);
    expect(screen.getByRole("radio", { name: "100%" })).toBeChecked();
    expect(screen.getByTestId("text-size-preview")).toBeInTheDocument();
  });

  it("applies a step to the store at once and remembers it as the person's choice", async () => {
    const user = userEvent.setup();
    mount();
    await user.click(screen.getByRole("radio", { name: "125%" }));
    expect(useThemeStore.getState().textScale).toBe(125);
    expect(screen.getByRole("radio", { name: "125%" })).toBeChecked();
    expect(useThemeStore.getState().textScaleChosen).toBe(true);
  });
});
