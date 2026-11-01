import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { cleanup, render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router";
import { afterEach, describe, expect, it } from "vitest";
import { i18n } from "@shared/lib";
import {
  DEV_SERVER_SCREENS_MARKER,
  DevServerScreensPage,
} from "./DevServerScreensPage";

describe("DevServerScreensPage", () => {
  afterEach(cleanup);

  it("показывает разделы серверных экранов в общем каркасе галереи", async () => {
    await i18n.changeLanguage("ru");
    const { container } = render(
      <MemoryRouter>
        <QueryClientProvider client={new QueryClient()}>
          <DevServerScreensPage />
        </QueryClientProvider>
      </MemoryRouter>,
    );
    expect(
      screen.getByRole("heading", { name: "Экраны серверного режима" }),
    ).toBeInTheDocument();
    expect(
      container.querySelector(
        `[data-dev-gallery="${DEV_SERVER_SCREENS_MARKER}"]`,
      ),
    ).not.toBeNull();
    expect(screen.getAllByText("Сервер недоступен").length).toBeGreaterThan(0);
    expect(
      screen.getByRole("link", { name: "Сессия и bootstrap" }),
    ).toHaveAttribute("href", "/dev/server-screens?section=session");
  });
});
