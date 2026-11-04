import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { cleanup, render, screen } from "@testing-library/react";
import { readFileSync } from "node:fs";
import { join } from "node:path";
import { I18nextProvider } from "react-i18next";
import { MemoryRouter } from "react-router";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { i18n } from "@shared/lib";
import { installViewport } from "@shared/lib/viewport/testing";
import {
  LOCAL_BOOTSTRAP,
  sessionKeys,
  type Bootstrap,
} from "@entities/session";
import { AppTitlebar } from "./AppTitlebar";

vi.mock("@features/account-menu", () => ({ AccountMenu: () => null }));
vi.mock("@features/guest-session", () => ({
  GuestBadge: () => null,
  useGuest: () => null,
}));
vi.mock("@features/help-center", () => ({ HelpButton: () => null }));
vi.mock("@features/inbox", () => ({ InboxBell: () => null }));
vi.mock("@features/onboarding", () => ({
  HelpMenu: () => <button type="button">help</button>,
}));
vi.mock("@entities/system", () => ({
  useSystemInfo: () => ({ data: { version: "0.0.0" } }),
}));

const serverUser = JSON.parse(
  readFileSync(
    join(
      import.meta.dirname,
      "../../../../..",
      "contracts/server/fixtures/Bootstrap/server_user.json",
    ),
    "utf8",
  ),
) as Bootstrap;

const mount = (bootstrap: Bootstrap, projectActions?: React.ReactNode) => {
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false, staleTime: Infinity } },
  });
  client.setQueryData(sessionKeys.bootstrap(), bootstrap);
  render(
    <QueryClientProvider client={client}>
      <I18nextProvider i18n={i18n}>
        <MemoryRouter>
          <AppTitlebar
            projectName="Курсовая"
            {...(projectActions ? { projectActions } : {})}
          />
        </MemoryRouter>
      </I18nextProvider>
    </QueryClientProvider>,
  );
};

describe("AppTitlebar on a phone", () => {
  let viewport: ReturnType<typeof installViewport> | undefined;
  beforeEach(async () => {
    await i18n.changeLanguage("ru");
  });
  afterEach(() => {
    cleanup();
    viewport?.restore();
    viewport = undefined;
  });

  it("hands the agent, settings and help to the account menu when there is one", () => {
    viewport = installViewport(390);
    mount(serverUser);
    const agent = document.querySelector("[data-tour=titlebar-agent]");
    const settings = document.querySelector("[data-tour=titlebar-settings]");
    expect(agent).toHaveClass("titlebar-secondary");
    expect(settings).toHaveClass("titlebar-secondary");
  });

  it("keeps them in the header of the local Studio, which has no account menu", () => {
    viewport = installViewport(390);
    mount(LOCAL_BOOTSTRAP);
    expect(
      document.querySelector("[data-tour=titlebar-agent]"),
    ).not.toHaveClass("titlebar-secondary");
    expect(
      document.querySelector("[data-tour=titlebar-settings]"),
    ).not.toHaveClass("titlebar-secondary");
  });

  it("moves the project actions to their own row under the header", () => {
    viewport = installViewport(360);
    mount(serverUser, <span data-testid="actions">people</span>);
    const row = screen.getByTestId("titlebar-subrow");
    expect(row).toContainElement(screen.getByTestId("actions"));
    expect(document.querySelector(".titlebar")).not.toContainElement(row);
  });

  it("keeps the project actions in the header on a desktop", () => {
    viewport = installViewport(1360);
    mount(serverUser, <span data-testid="actions">people</span>);
    expect(screen.queryByTestId("titlebar-subrow")).toBeNull();
    expect(document.querySelector(".titlebar")).toContainElement(
      screen.getByTestId("actions"),
    );
  });
});
