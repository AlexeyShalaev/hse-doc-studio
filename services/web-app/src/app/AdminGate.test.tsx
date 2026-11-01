import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { cleanup, render, screen, waitFor } from "@testing-library/react";
import { I18nextProvider } from "react-i18next";
import { RouterProvider, createMemoryRouter } from "react-router";
import { afterEach, describe, expect, it, vi } from "vitest";
import { i18n } from "@shared/lib";
import {
  LOCAL_BOOTSTRAP,
  sessionKeys,
  type Bootstrap,
} from "@entities/session";
import { AdminGate } from "./AdminGate";

// Считаем загрузки чанка админки: у не-админа модуль не должен даже вычисляться.
const loaded = vi.hoisted(() => ({ count: 0 }));
vi.mock("@pages/AdminPage", async () => {
  const actual =
    await vi.importActual<Record<string, unknown>>("@pages/AdminPage");
  loaded.count += 1;
  return actual;
});
vi.mock("@widgets/AppTitlebar", () => ({ AppTitlebar: () => null }));
vi.mock("@widgets/AppStatusBar", () => ({ AppStatusBar: () => null }));

const bootstrap = (admin: boolean): Bootstrap => ({
  ...LOCAL_BOOTSTRAP,
  mode: "server",
  capabilities: { ...LOCAL_BOOTSTRAP.capabilities, admin },
});

const mount = (data: Bootstrap | null, path = "/admin") => {
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false, staleTime: Infinity } },
  });
  if (data) client.setQueryData(sessionKeys.bootstrap(), data);
  const router = createMemoryRouter(
    [{ path: "/admin/*", element: <AdminGate /> }],
    { initialEntries: [path] },
  );
  render(
    <QueryClientProvider client={client}>
      <I18nextProvider i18n={i18n}>
        <RouterProvider router={router} />
      </I18nextProvider>
    </QueryClientProvider>,
  );
};

describe("AdminGate", () => {
  afterEach(async () => {
    cleanup();
    await i18n.changeLanguage("ru");
  });

  it("shows not-found to a non-admin and never loads the admin chunk", async () => {
    mount(bootstrap(false));
    expect(await screen.findByText("404")).toBeInTheDocument();
    expect(screen.queryByTestId("admin-layout")).not.toBeInTheDocument();
    expect(loaded.count).toBe(0);
  });

  it("renders the admin shell for an admin, in ru", async () => {
    mount(bootstrap(true));
    expect(await screen.findByTestId("admin-overview")).toBeInTheDocument();
    expect(screen.getByText("Обзор установки")).toBeInTheDocument();
    expect(screen.getByTestId("admin-nav-users")).toHaveTextContent(
      "Пользователи",
    );
  });

  it("renders the admin shell in en", async () => {
    await i18n.changeLanguage("en");
    mount(bootstrap(true));
    expect(
      await screen.findByText("Installation overview"),
    ).toBeInTheDocument();
    expect(screen.getByTestId("admin-nav-audit")).toHaveTextContent("Audit");
  });

  it("redirects an unknown section to the overview", async () => {
    mount(bootstrap(true), "/admin/nope");
    await waitFor(() => {
      expect(screen.getByTestId("admin-overview")).toBeInTheDocument();
    });
  });
});
